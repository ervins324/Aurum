"""MCC → Aurum category-name mapping.

Derived from MCC_CODES.md (Ukrainian MCC catalogue).  Maps integer MCC
codes to the *expected* Aurum category name (case-insensitive match at
runtime against the user's existing categories).

Only a curated subset of the ~250 codes in the catalogue is mapped — the
most common consumer MCCs.  If a code is not in this dict, the transaction
is imported without a category (same as before).

No new categories are created automatically — the category must already
exist in the database.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.enums import CategoryKind, TransactionType

# Maps MCC int → English category name (matches Aurum seed defaults).
MCC_CATEGORY_MAP: dict[int, str] = {
    # ── Food & Groceries ──
    5411: "Groceries",          # Supermarkets
    5412: "Groceries",          # Hybrid supermarkets
    5422: "Groceries",          # Meat markets
    5441: "Groceries",          # Candy / confectionery
    5451: "Groceries",          # Dairy
    5462: "Groceries",          # Bakeries
    5499: "Groceries",          # Misc food stores
    5298: "Groceries",          # Internet shopping grocery
    5300: "Groceries",          # Wholesalers

    # ── Dining Out ──
    5811: "Dining Out",         # Caterers
    5812: "Dining Out",         # Restaurants
    5813: "Dining Out",         # Bars, nightclubs
    5814: "Dining Out",         # Fast food

    # ── Housing & Utilities ──
    4900: "Housing & Utilities",  # Utilities — electric, gas, water
    4814: "Housing & Utilities",  # Phone card calls
    4815: "Housing & Utilities",  # Monthly phone bills
    4816: ("Subscriptions", "Housing & Utilities"),  # Computer network / ISP / cloud file-sharing (CEMEA High Risk)
    4899: "Housing & Utilities",  # Cable / pay TV
    1520: "Housing & Utilities",  # General contractors — residential
    1711: "Housing & Utilities",  # HVAC / plumbing
    1731: "Housing & Utilities",  # Electrical contractors
    1740: "Housing & Utilities",  # Insulation / plastering / tiling
    1750: "Housing & Utilities",  # Carpentry
    1761: "Housing & Utilities",  # Roofing / siding
    7349: "Housing & Utilities",  # Cleaning / janitorial

    # ── Transportation ──
    4111: "Transportation",     # Commuter / suburban transport
    4112: "Transportation",     # Passenger railways
    4121: "Transportation",     # Taxis / limousines
    4131: "Transportation",     # Bus lines
    4214: ("Logistics", "Transportation"),  # Local delivery / freight
    4215: ("Logistics", "Transportation"),  # Courier services / logistics / freight delivery
    9402: ("Logistics", "Transportation"),  # Postal Services — Government Only
    4511: ("Airlines", "Travel", "Transportation"),  # Airlines general industry code
    3000: ("Airlines", "Travel", "Transportation"),  # Airlines
    4582: "Transportation",     # Airport terminals
    4722: ("Travel", "Transportation"),  # Travel agencies
    4784: "Transportation",     # Tolls
    4789: "Transportation",     # Transportation services NEC
    5541: "Transportation",     # Gas stations / service stations (Visa Mandatory)
    5542: "Transportation",     # Automated fuel dispensers / AFD (Visa Mandatory)
    5552: "Transportation",     # EV charging (Visa Mandatory)
    7011: ("Hotels", "Travel", "Transportation", "Housing & Utilities"),  # Hotels / motels / resorts general
    7512: ("Car Rental", "Travel", "Transportation"),  # Car rental general industry code
    7523: "Transportation",     # Parking
    7531: "Transportation",     # Auto service stations
    7538: "Transportation",     # Auto repair general
    7542: "Transportation",     # Car wash

    # ── Health & Fitness ──
    5122: "Health & Fitness",    # Pharmacies (wholesale) — CEMEA High Risk
    5912: "Health & Fitness",    # Pharmacies (retail / online) — CEMEA High Risk
    8011: "Health & Fitness",    # Doctors
    8021: "Health & Fitness",    # Dentists
    8031: "Health & Fitness",    # Osteopaths
    8041: "Health & Fitness",    # Chiropractors
    8042: "Health & Fitness",    # Optometrists
    8043: "Health & Fitness",    # Optical goods
    8049: "Health & Fitness",    # Podiatrists
    8050: "Health & Fitness",    # Nursing / personal care
    8062: "Health & Fitness",    # Hospitals
    8071: "Health & Fitness",    # Medical / dental labs
    8099: "Health & Fitness",    # Medical services NEC
    7298: "Health & Fitness",    # Health clubs

    # ── Shopping ──
    5200: "Shopping",           # Home supply stores
    5211: "Shopping",           # Building materials
    5251: "Shopping",           # Hardware stores
    5261: "Shopping",           # Garden supplies
    5262: "Shopping",           # Marketplaces / payment facilitators (Visa Mandatory)
    5297: "Shopping",           # Retail internet volume
    5309: "Shopping",           # Duty-free
    5310: "Shopping",           # Discount stores
    5311: "Shopping",           # Department stores
    5331: "Shopping",           # Variety stores
    5399: "Shopping",           # General merchandise
    5611: "Shopping",           # Men's clothing
    5621: "Shopping",           # Women's clothing
    5631: "Shopping",           # Women's accessories
    5641: "Shopping",           # Children's clothing
    5651: "Shopping",           # Family clothing
    5661: "Shopping",           # Shoe stores
    5691: "Shopping",           # Men's / women's clothing
    5699: "Shopping",           # Misc clothing
    5712: "Shopping",           # Furniture / home furnishings
    5713: "Shopping",           # Floor covering
    5714: "Shopping",           # Drapery / upholstery
    5719: "Shopping",           # Misc home furnishing
    5722: "Shopping",           # Household appliances
    5732: "Shopping",           # Electronics
    5733: "Shopping",           # Musical instruments
    5734: "Shopping",           # Computer software stores
    5735: "Shopping",           # Record stores
    5931: "Shopping",           # Second-hand stores
    5940: "Shopping",           # Bicycle shops
    5941: "Shopping",           # Sporting goods
    5942: "Shopping",           # Bookstores
    5943: "Shopping",           # Office / school supplies
    5944: "Shopping",           # Jewellery / watches
    5945: "Shopping",           # Toy stores
    5947: "Shopping",           # Gift / novelty shops
    5948: "Shopping",           # Leather goods / luggage
    5949: "Shopping",           # Fabric / sewing
    5966: "Shopping",           # Direct marketing — outbound telemarketing (CEMEA High Risk)
    5970: "Shopping",           # Art / craft supplies
    5977: "Shopping",           # Cosmetics
    5992: "Shopping",           # Florists
    5993: "Shopping",           # Tobacco / cigar stores / e-cigarettes (CEMEA High Risk)
    5995: "Shopping",           # Pet shops
    5999: "Shopping",           # Misc retail

    # ── Entertainment ──
    7832: "Entertainment",      # Cinema
    7841: "Entertainment",      # Video rental
    7911: "Entertainment",      # Dance halls / schools
    7922: "Entertainment",      # Theatrical agencies
    7929: "Entertainment",      # Bands / orchestras
    7932: "Entertainment",      # Billiard / pool
    7933: "Entertainment",      # Bowling
    7941: "Entertainment",      # Sports venues / pro sports
    7991: "Entertainment",      # Tourist attractions
    7993: "Entertainment",      # Video game supplies
    7994: "Entertainment",      # Video game arcades
    7995: ("Gambling", "Betting", "Entertainment"),  # Online gambling, betting, casinos, bookmakers (Visa Mandatory & CEMEA High Risk)
    7996: "Entertainment",      # Amusement parks / carnivals
    7997: ("Health & Fitness", "Entertainment"),  # Clubs — country / sports
    7998: "Entertainment",      # Aquariums / zoos
    7999: "Entertainment",      # Recreation NEC
    9406: ("Lottery", "Gambling", "Entertainment"),  # State lotteries outside US (Visa Mandatory)
    5045: "Entertainment",      # Computers / peripherals (gaming / hobby)

    # ── Subscriptions ──
    5815: "Subscriptions",      # Digital goods — A/V media
    5816: ("Subscriptions", "Entertainment"),  # Digital goods — games / skilled gaming (CEMEA High Risk)
    5817: "Subscriptions",      # Digital goods — apps
    5818: "Subscriptions",      # Digital goods — multi-category
    5967: ("Subscriptions", "Entertainment"),  # Adult content & services (CEMEA High Risk)
    5968: "Subscriptions",      # Continuity / subscription merchants / negative option (CEMEA High Risk)
    7273: ("Subscriptions", "Entertainment", "Shopping"),  # Dating services & escort (CEMEA High Risk)
    7372: "Subscriptions",      # Programming / data processing / SaaS

    # ── Beauty (mapped to Shopping if no dedicated category) ──
    7230: "Shopping",           # Barber / beauty shops
    7297: "Shopping",           # Massage parlours

    # ── Education (mapped to Shopping if no dedicated category) ──
    8211: "Shopping",           # Elementary / secondary schools
    8220: "Shopping",           # Colleges / universities
    8249: "Shopping",           # Trade / vocational schools
    8299: "Shopping",           # Child care

    # ── Veterinary ──
    742: "Shopping",            # Veterinary services

    # ── Financial services, cash & crypto (Visa Mandatory & CEMEA High Risk) ──
    4829: ("Money Transfers", "Transfers"),  # Wire / money transfers / P2P / Visa Direct
    6010: ("Cash", "Money Transfers", "Finance"),  # Manual cash disbursement — bank teller
    6011: ("Cash", "Money Transfers", "Finance"),  # Automated cash disbursement — ATM
    6012: ("Finance", "Financial Services", "Financial"),  # Financial institutions — merchandise, services, loan repayment
    6051: ("Crypto", "Investments", "Finance"),  # Quasi-cash, crypto wallets, on-ramp
    6211: ("Investments", "Finance"),  # Securities brokers / Forex / trading

    # ── Professional Services ──
    8999: ("Professional Services", "Services"),  # Professional Services - Not Elsewhere Classified
}


def resolve_target_by_mcc(mcc: int) -> str | tuple[str, ...] | None:
    """Resolve an MCC to candidate Aurum category name(s).

    1. Checks explicit MCC definitions in MCC_CATEGORY_MAP.
    2. Falls back to industry ranges defined in MCC_CODES.md (Visa Merchant
       Data Standards Manual / ISO 18245):
       - 3000-3350: Airlines (individual carrier codes)
       - 3351-3499: Car rental (individual agency codes)
       - 3501-3883: Hotels & resorts (individual chain codes)
       - 8000-8099: Healthcare & medical services
       - 5600-5699: Clothing, shoes & accessories
       - 5700-5799: Furniture, home appliances & electronics
       - 5800-5814: Dining, restaurants & fast food
       - 5400-5499: Food & grocery stores
       - 5500-5599: Automotive dealers, gas & EV charging
       - 7500-7549: Automotive services & parking
       - 7800-7999: Entertainment & recreation
       - 1500-1799: Construction & home improvement contractors

    Returns None for invalid or unmapped codes.
    """
    if mcc in MCC_CATEGORY_MAP:
        return MCC_CATEGORY_MAP[mcc]

    # Standard MCCs are strictly 4 digits (0001 - 9999)
    if not (1 <= mcc <= 9999):
        return None

    # Industry range fallbacks
    if 3000 <= mcc <= 3350:
        return ("Airlines", "Travel", "Transportation")
    if 3351 <= mcc <= 3499:
        return ("Car Rental", "Travel", "Transportation")
    if 3501 <= mcc <= 3883:
        return ("Hotels", "Travel", "Transportation", "Housing & Utilities")
    if 8000 <= mcc <= 8099:
        return "Health & Fitness"
    if 5600 <= mcc <= 5699:
        return "Shopping"
    if 5700 <= mcc <= 5799:
        return "Shopping"
    if 5800 <= mcc <= 5814:
        return "Dining Out"
    if 5400 <= mcc <= 5499:
        return "Groceries"
    if 5500 <= mcc <= 5599:
        return "Transportation"
    if 7500 <= mcc <= 7549:
        return "Transportation"
    if 7800 <= mcc <= 7999:
        return "Entertainment"
    if 1500 <= mcc <= 1799:
        return "Housing & Utilities"

    return None


async def resolve_category_id_by_mcc(
    session: AsyncSession,
    mcc: int | None,
    tx_type: TransactionType,
) -> int | None:
    """Look up a category_id by MCC code.

    Matches candidate category names from MCC_CATEGORY_MAP or industry range
    blocks against the user's existing categories (case-insensitive). Only
    matches categories whose kind aligns with the transaction type (EXPENSE for
    expenses, INCOME for income).

    For MCC 4829 (wire / money transfers) the category is auto-created if it
    doesn't exist yet — see resolve_or_create_money_transfers_category.

    Returns None if no MCC mapping exists or no matching category is found.
    """
    if mcc is None:
        return None

    # MCC 4829 always gets the dedicated "Money Transfers" category,
    # auto-creating it when it's absent (handles existing installs that
    # pre-date the seeded default).
    if mcc == 4829:
        return await resolve_or_create_money_transfers_category(session, tx_type)

    target = resolve_target_by_mcc(mcc)
    if target is None:
        return None

    candidates = [target] if isinstance(target, str) else list(target)
    expected_kind = (
        CategoryKind.EXPENSE if tx_type == TransactionType.EXPENSE else CategoryKind.INCOME
    )

    for candidate in candidates:
        result = await session.execute(
            select(Category.id).where(
                func.lower(Category.name) == candidate.lower(),
                Category.kind == expected_kind,
            ).limit(1)
        )
        cat_id = result.scalar_one_or_none()
        if cat_id is not None:
            return cat_id
    return None


async def resolve_or_create_money_transfers_category(
    session: AsyncSession,
    tx_type: TransactionType,
) -> int:
    """Find or create the 'Money Transfers' category for MCC 4829.

    Searches existing categories by the canonical names used by the seed
    (case-insensitive). If none is found, automatically creates the category
    so that wire-transfer transactions are always categorised correctly,
    even on installs that pre-date the seeded 'Money Transfers' default.
    """
    expected_kind = (
        CategoryKind.EXPENSE if tx_type == TransactionType.EXPENSE else CategoryKind.INCOME
    )
    candidate_names = ["money transfers", "transfers", "wire transfers"]

    result = await session.execute(
        select(Category.id).where(
            func.lower(Category.name).in_(candidate_names),
            Category.kind == expected_kind,
        ).order_by(Category.id.asc()).limit(1)
    )
    cat_id = result.scalar_one_or_none()
    if cat_id is not None:
        return cat_id

    # Auto-create the category so MCC 4829 is always mapped on any install
    new_cat = Category(
        name="Money Transfers",
        kind=expected_kind,
        icon="arrow-left-right",
        color="#6b7280",
        sort_order=98,
        is_default=True,
    )
    session.add(new_cat)
    await session.flush()
    return new_cat.id


async def get_money_transfer_category_ids(session: AsyncSession) -> set[int]:
    """Return all category IDs representing Money Transfers (including subcategories).

    Used when excluding money transfers / wire operations from cash flow, dashboard
    summaries, or reports to avoid skewing income and living expenses with neutral
    account-funding operations.
    """
    candidate_names = {"money transfers", "transfers", "wire transfers", "денежные переводы", "переводы"}
    result = await session.execute(select(Category.id, Category.parent_id, Category.name))
    all_cats = result.all()
    transfer_ids = {
        row[0] for row in all_cats if row[2] and row[2].strip().lower() in candidate_names
    }
    child_ids = {row[0] for row in all_cats if row[1] in transfer_ids}
    return transfer_ids | child_ids


async def resolve_fallback_other_category(
    session: AsyncSession,
    tx_type: TransactionType,
) -> int:
    """Find or create an 'Other' category for transactions without a category.

    Searches existing user categories for names like 'Other', 'Others', 'Other Expense',
    'Разное', 'Другое'. If none exists in the database, automatically creates a default
    'Other' category so that every transaction is categorized.
    """
    expected_kind = (
        CategoryKind.EXPENSE if tx_type == TransactionType.EXPENSE else CategoryKind.INCOME
    )
    candidate_names = (
        ["other", "others", "other expense", "other expenses", "разное", "другое"]
        if expected_kind == CategoryKind.EXPENSE
        else ["other income", "other", "others", "другой доход", "разное", "другое"]
    )

    result = await session.execute(
        select(Category.id).where(
            func.lower(Category.name).in_(candidate_names),
            Category.kind == expected_kind,
        ).order_by(Category.id.asc()).limit(1)
    )
    cat_id = result.scalar_one_or_none()
    if cat_id is not None:
        return cat_id

    # Create default fallback category
    fallback_name = "Other" if expected_kind == CategoryKind.EXPENSE else "Other Income"
    fallback_icon = "more-horizontal" if expected_kind == CategoryKind.EXPENSE else "plus-circle"
    new_cat = Category(
        name=fallback_name,
        kind=expected_kind,
        icon=fallback_icon,
        color="#898781",
        sort_order=99,
        is_default=True,
    )
    session.add(new_cat)
    await session.flush()
    return new_cat.id
