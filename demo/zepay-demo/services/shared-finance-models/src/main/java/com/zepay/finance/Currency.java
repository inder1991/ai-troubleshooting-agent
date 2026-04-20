package com.zepay.finance;

/**
 * Supported currencies for the Zepay demo. Only USD is exercised
 * in the scenario; EUR/JPY are here so the Money class compiles
 * against a realistic enum and so the plus() call sites look natural.
 */
public enum Currency {
    USD,
    EUR,
    JPY
}
