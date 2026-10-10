import { varAlpha } from 'minimal-shared/utils';

// ----------------------------------------------------------------------

const MuiLink = {
  // ▼▼▼▼▼▼▼▼ ⚙️ PROPS ▼▼▼▼▼▼▼▼
  defaultProps: {
    underline: 'hover',
  },
  // ▼▼▼▼▼▼▼▼ 🎨 STYLE ▼▼▼▼▼▼▼▼
  styleOverrides: {
    root: {
      '--Link-underlineColor': varAlpha('currentColor', 0.4),
    },
  },
};

/* **********************************************************************
 * 🚀 Export
 * **********************************************************************/
export const link = {
  MuiLink,
};
