'use client';

import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';

// ----------------------------------------------------------------------

/**
 * Board "Mulai" — the thread before there is anything to track.
 *
 * A chat with nothing in it is the hardest screen in the product: the
 * box is empty, the app has no data, and neither one can start. So the
 * first turn asks the one question that unblocks everything — where the
 * money is — and these chips are the answer half-written.
 *
 * Tapping one puts the name in the composer rather than sending it. The
 * wallet still needs a balance, and asking the model to ask for it is a
 * round trip to say what a cursor already says.
 */
export const WALLET_SUGGESTIONS = ['BCA', 'Mandiri', 'GoPay', 'Cash', 'Kartu kredit'];

export const FIRST_RUN_GREETING = [
  {
    id: 'mulai-1',
    role: 'assistant',
    body: 'Halo. Sebelum mulai nyatet, gua perlu tahu uang lu ada di mana aja.',
  },
  {
    id: 'mulai-2',
    role: 'assistant',
    body: 'Satu dulu juga nggak apa-apa — sisanya bisa nyusul kapan aja.',
  },
];

export function WalletSuggestions({ onPick, disabled = false }) {
  return (
    // Indented to the greeting's text column, so the chips read as part
    // of what was just said rather than as a toolbar.
    <Stack direction="row" sx={{ pl: '36px', gap: 1, flexWrap: 'wrap' }}>
      {WALLET_SUGGESTIONS.map((name) => (
        <Box
          key={name}
          component="button"
          type="button"
          disabled={disabled}
          onClick={() => onPick(name)}
          sx={{
            px: 2,
            minHeight: 40,
            fontSize: 14,
            fontWeight: 700,
            cursor: 'pointer',
            borderRadius: 999,
            border: '1.5px solid',
            borderColor: 'grey.300',
            color: 'text.primary',
            bgcolor: 'background.paper',
          }}
        >
          {name}
        </Box>
      ))}
    </Stack>
  );
}
