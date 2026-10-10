// ----------------------------------------------------------------------

/**
 * Money helpers.
 *
 * Amounts are handled as an INTEGER NUMBER OF RUPIAH everywhere in the app
 * (PRD FR03 forbids floating point for money). These helpers are the only
 * place that turns those integers into text, so a stray float shows up here
 * loudly instead of silently rounding somewhere in the UI.
 *
 * Note that JS numbers are safe for integer rupiah well past any realistic
 * personal balance (2^53 - 1 is about 9 quadrillion), but any arithmetic
 * must still stay in integers — never multiply by a rate and keep the
 * fraction.
 */

const FORMATTER = new Intl.NumberFormat('id-ID', {
  style: 'decimal',
  maximumFractionDigits: 0,
});

/**
 * Throws on a non-integer amount rather than rounding it away, so a
 * floating-point value cannot quietly reach the user.
 */
function assertIntegerRupiah(amount) {
  if (!Number.isInteger(amount)) {
    throw new TypeError(
      `Nominal harus bilangan bulat rupiah, bukan ${amount}. ` +
        'Lihat PRD FR03: uang tidak boleh disimpan sebagai floating point.'
    );
  }
}

/**
 * Formats integer rupiah with a currency prefix: 35000 -> "Rp35.000".
 *
 * @param {number} amount integer rupiah
 * @param {{ signed?: boolean }} [options] `signed` keeps an explicit +/-,
 *   used where a delta's direction matters.
 */
export function formatRupiah(amount, options = {}) {
  assertIntegerRupiah(amount);

  const { signed = false } = options;
  const sign = signed && amount > 0 ? '+' : amount < 0 ? '-' : '';

  return `${sign}Rp${FORMATTER.format(Math.abs(amount))}`;
}

/**
 * Formats without the currency prefix, for places that already label the
 * unit: 35000 -> "35.000".
 */
export function formatRupiahPlain(amount) {
  assertIntegerRupiah(amount);
  return FORMATTER.format(amount);
}
