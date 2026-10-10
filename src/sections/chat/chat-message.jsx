import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

// ----------------------------------------------------------------------

/**
 * A single chat bubble.
 *
 * `role` is 'user' or 'assistant'. Assistant turns may instead carry a card
 * (a draft, a summary), which ChatThread renders full width rather than as a
 * bubble, so this component only handles text.
 */
export function ChatMessage({ role, body, time }) {
  const isUser = role === 'user';

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
      }}
    >
      <Box
        sx={(theme) => ({
          px: 1.5,
          py: 1.25,
          maxWidth: '85%',
          borderRadius: 2,
          ...(isUser
            ? {
                color: theme.vars.palette.primary.darker,
                bgcolor: varAlpha(theme.vars.palette.primary.mainChannel, 0.16),
                borderBottomRightRadius: theme.spacing(0.5),
              }
            : {
                bgcolor: varAlpha(theme.vars.palette.grey['500Channel'], 0.12),
                borderBottomLeftRadius: theme.spacing(0.5),
              }),
        })}
      >
        {/* 16px minimum body text per FR17, and `pre-wrap` so a multi-line
            message the user typed keeps its shape. */}
        <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {body}
        </Typography>

        {time && (
          <Typography
            variant="caption"
            component="time"
            sx={{ mt: 0.5, display: 'block', opacity: 0.64 }}
          >
            {time}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
