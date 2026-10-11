// ----------------------------------------------------------------------

export const themeConfig = {
  /** **************************************
   * Base
   *************************************** */
  defaultMode: 'light',
  modeStorageKey: 'theme-mode',
  direction: 'ltr',
  classesPrefix: 'minimal',
  /** **************************************
   * Css variables
   *************************************** */
  cssVariables: {
    cssVarPrefix: '',
    colorSchemeSelector: 'data-color-scheme',
  },
  /** **************************************
   * Typography
   *************************************** */
  /**
   * Plus Jakarta Sans stands in for Maison Neue, the typeface Gojek's
   * Asphalt uses and which is licensed. It is a geometric grotesque
   * from Tokotype, drawn for Jakarta's city identity, and it is the
   * closest free match in both proportion and temperament.
   */
  fontFamily: {
    primary: 'Plus Jakarta Sans Variable',
    secondary: 'Barlow',
  },
  /** **************************************
   * Palette
   *************************************** */
  palette: {
    /**
     * lega green. Deliberately not Gojek's #00AA13: the interface
     * borrows how Asphalt is put together, but a brand colour is not a
     * pattern to borrow.
     *
     * `main` on white is 3.6:1 — fine for large text, icons and fills,
     * short of AA for body copy. Anything carrying a sentence in white
     * uses ink, and text on `lighter` uses `dark` (6.6:1).
     */
    primary: {
      lighter: '#D9F3E6',
      light: '#5FD3A2',
      main: '#009A5B',
      dark: '#006B45',
      darker: '#00482F',
      contrastText: '#FFFFFF',
    },
    secondary: {
      lighter: '#EFD6FF',
      light: '#C684FF',
      main: '#8E33FF',
      dark: '#5119B7',
      darker: '#27097A',
      contrastText: '#FFFFFF',
    },
    info: {
      lighter: '#CAFDF5',
      light: '#61F3F3',
      main: '#00B8D9',
      dark: '#006C9C',
      darker: '#003768',
      contrastText: '#FFFFFF',
    },
    success: {
      lighter: '#D3FCD2',
      light: '#77ED8B',
      main: '#22C55E',
      dark: '#118D57',
      darker: '#065E49',
      contrastText: '#ffffff',
    },
    warning: {
      lighter: '#FFF5CC',
      light: '#FFD666',
      main: '#FFAB00',
      dark: '#B76E00',
      darker: '#7A4100',
      contrastText: '#1C252E',
    },
    error: {
      lighter: '#FFE9D5',
      light: '#FFAC82',
      main: '#FF5630',
      dark: '#B71D18',
      darker: '#7A0916',
      contrastText: '#FFFFFF',
    },
    grey: {
      50: '#FCFDFD',
      100: '#F9FAFB',
      200: '#F4F6F8',
      300: '#DFE3E8',
      400: '#C4CDD5',
      500: '#919EAB',
      600: '#637381',
      700: '#454F5B',
      800: '#1C252E',
      900: '#141A21',
    },
    common: {
      black: '#000000',
      white: '#FFFFFF',
    },
  },
};
