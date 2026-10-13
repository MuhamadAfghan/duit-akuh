// ----------------------------------------------------------------------

/**
 * The width of the app, everywhere.
 *
 * Phone is the primary device (PRD section 12), so every surface is drawn in
 * one phone column that simply centres on a wider window. The auth screens
 * were already 430 — the top of the mandated 320-430 CSS px range — while
 * the shell stood at 720, so signing in silently widened the page under you.
 *
 * This is the one number, imported by everything that has to agree with it:
 * the shell, the sheets that portal out of it to the body, and the auth
 * column itself. A literal written anywhere else is a fourth thing to keep
 * in step.
 */
export const APP_COLUMN_WIDTH = 430;
