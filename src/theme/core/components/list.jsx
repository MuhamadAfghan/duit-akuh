// ----------------------------------------------------------------------

const MuiListItemIcon = {
  // ▼▼▼▼▼▼▼▼ 🎨 STYLE ▼▼▼▼▼▼▼▼
  styleOverrides: {
    root: ({ theme }) => ({
      color: 'inherit',
      minWidth: 'auto',
      marginRight: theme.spacing(2),
    }),
  },
};

const MuiListItemAvatar = {
  // ▼▼▼▼▼▼▼▼ 🎨 STYLE ▼▼▼▼▼▼▼▼
  styleOverrides: {
    root: ({ theme }) => ({
      minWidth: 'auto',
      marginRight: theme.spacing(2),
    }),
  },
};

const MuiListItemText = {
  // ▼▼▼▼▼▼▼▼ ⚙️ PROPS ▼▼▼▼▼▼▼▼
  defaultProps: {
    slotProps: {
      primary: { sx: { typography: 'subtitle2' } },
    },
  },
  // ▼▼▼▼▼▼▼▼ 🎨 STYLE ▼▼▼▼▼▼▼▼
  styleOverrides: {
    root: { margin: 0 },
    multiline: { margin: 0 },
  },
};

/* **********************************************************************
 * 🚀 Export
 * **********************************************************************/
export const list = {
  MuiListItemIcon,
  MuiListItemText,
  MuiListItemAvatar,
};
