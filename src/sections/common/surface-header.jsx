import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

// ----------------------------------------------------------------------

/** Shared header for the Ringkasan and Data surfaces, matching the chat's. */
export function SurfaceHeader({ title, action }) {
  return (
    <Box
      component="header"
      sx={(theme) => ({
        flexShrink: 0,
        px: 2,
        pt: 'calc(env(safe-area-inset-top) + 12px)',
        pb: 1.5,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1,
        bgcolor: theme.vars.palette.background.paper,
        borderBottom: `solid 1px ${theme.vars.palette.divider}`,
      })}
    >
      <Typography variant="h6" component="h1">
        {title}
      </Typography>
      {action}
    </Box>
  );
}
