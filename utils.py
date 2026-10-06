from decimal import Decimal, InvalidOperation

def parse_bet_input(value: str, user_balance: float = 0) -> int:
    """
    Поддерживаемые форматы:
    • 100
    • 1к / 1k       = 1 000
    • 1кк / 1kk     = 1 000 000
    • 1ккк / 1kkk   = 1 000 000 000 (миллиард)
    • 1м / 1m       = 1 000 000
    • 1млрд / 1b    = 1 000 000 000
    • всё / все     = весь баланс
    """
    text = str(value).strip().lower()
    text = text.replace(" ", "").replace(",", ".")

    if text in ("все", "всё", "all"):
        return max(0, int(user_balance))

    multipliers = (
        ("млрд", Decimal("1000000000")),
        ("миллиард", Decimal("1000000000")),
        ("ккк", Decimal("1000000000")),
        ("kkk", Decimal("1000000000")),
        ("б", Decimal("1000000000")),
        ("b", Decimal("1000000000")),
        ("млн", Decimal("1000000")),
        ("миллион", Decimal("1000000")),
        ("кк", Decimal("1000000")),
        ("kk", Decimal("1000000")),
        ("м", Decimal("1000000")),
        ("m", Decimal("1000000")),
        ("к", Decimal("1000")),
        ("k", Decimal("1000")),
    )

    for suffix, multiplier in multipliers:
        if text.endswith(suffix):
            number = text[:-len(suffix)]
            if not number:
                return 0
            try:
                result = Decimal(number) * multiplier
                return max(0, int(result))
            except InvalidOperation:
                return 0

    try:
        return max(0, int(Decimal(text)))
    except InvalidOperation:
        return 0
