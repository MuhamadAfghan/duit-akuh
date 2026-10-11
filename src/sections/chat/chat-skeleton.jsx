import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import { visuallyHidden } from '@mui/utils';
import Skeleton from '@mui/material/Skeleton';

// ----------------------------------------------------------------------

/** Nothing regular: a thread of identical bars reads as a loading bar. */
const SHAPE = [
  { role: 'assistant', width: '72%', height: 46 },
  { role: 'user', width: '54%', height: 42 },
  { role: 'assistant', width: '84%', height: 68 },
  { role: 'user', width: '46%', height: 42 },
  { role: 'assistant', width: '66%', height: 46 },
];

const reducedMotion = {
  '@media (prefers-reduced-motion: reduce)': { '&::after': { animation: 'none' } },
};

/**
 * The thread while its first page is on the way.
 *
 * It replaces a worse thing than a spinner: the view used to open on
 * the welcome message and then swap it for the real history, so every
 * launch flashed a greeting at someone who had been using the app for
 * months.
 *
 * Bottom-anchored and uneven, because that is what a conversation
 * looks like — a column of equal bars would read as a progress
 * indicator wearing a costume.
 */
export function ChatSkeleton() {
  return (
    <Box
      sx={{
        flex: '1 1 auto',
        minHeight: 0,
        gap: 1.5,
        px: 2,
        py: 2,
        display: 'flex',
        overflow: 'hidden',
        flexDirection: 'column',
        justifyContent: 'flex-end',
      }}
    >
      <Box role="status" aria-live="polite" sx={visuallyHidden}>
        Memuat percakapan…
      </Box>

      {SHAPE.map((bubble, index) =>
        bubble.role === 'user' ? (
          <Stack key={index} aria-hidden direction="row" sx={{ justifyContent: 'flex-end' }}>
            <Skeleton
              variant="rounded"
              animation="wave"
              width={bubble.width}
              height={bubble.height}
              sx={[reducedMotion, { borderRadius: '18px 18px 6px 18px' }]}
            />
          </Stack>
        ) : (
          <Stack key={index} aria-hidden direction="row" sx={{ gap: 1, alignItems: 'flex-end' }}>
            <Skeleton
              variant="circular"
              animation="wave"
              width={26}
              height={26}
              sx={[reducedMotion, { flexShrink: 0, mb: 0.25 }]}
            />
            <Skeleton
              variant="rounded"
              animation="wave"
              width={bubble.width}
              height={bubble.height}
              sx={(theme) => ({
                ...reducedMotion,
                borderRadius: '18px 18px 18px 6px',
                // The real assistant bubble is white on the grey canvas,
                // so its placeholder is lighter than the person's.
                bgcolor: varAlpha(theme.vars.palette.grey['500Channel'], 0.13),
              })}
            />
          </Stack>
        )
      )}
    </Box>
  );
}
