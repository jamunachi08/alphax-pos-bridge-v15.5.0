"""
Helpers for terminal adapters that need to know how many minor units
a currency has (e.g. cents, halalas).

Most currencies have 2 minor units (USD cents, EUR cents, SAR halalas,
AED fils). A few have 0 (JPY) or 3 (KWD, BHD, OMR — Gulf currencies
with a quarter-fils-style split).

This list comes from ISO 4217. We don't try to be exhaustive — just
the currencies that ship with our app's POS Profile defaults plus
common GCC/MENA currencies. Unknown currencies default to 2.
"""

# ISO 4217 currency code -> number of minor unit decimals.
_MINOR_UNITS = {
    # 0 — no fractional unit
    "JPY": 0, "KRW": 0, "VND": 0, "ISK": 0, "CLP": 0, "PYG": 0,
    "RWF": 0, "UGX": 0, "DJF": 0, "GNF": 0, "XAF": 0, "XOF": 0,
    # 3 — Gulf high-precision currencies
    "BHD": 3, "KWD": 3, "OMR": 3, "JOD": 3, "TND": 3, "LYD": 3, "IQD": 3,
    # 4 — esoteric (Chilean unit of account, Uruguayan indexed unit)
    "CLF": 4, "UYW": 4,
    # everyone else: 2 (USD, EUR, SAR, AED, EGP, INR, GBP, etc)
}


def currency_minor_units(currency_code: str) -> int:
    """Return the number of decimal places to use when converting major
    units (the amount the cashier sees) to minor units (what most
    payment APIs accept on the wire)."""
    if not currency_code:
        return 2
    return _MINOR_UNITS.get(currency_code.upper(), 2)
