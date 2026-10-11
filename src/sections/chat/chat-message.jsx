import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

// ----------------------------------------------------------------------

/**
 * One turn in the thread.
 *
 * `role` is 'user' or 'assistant'. Assistant turns may instead carry a card
 * (a draft, a summary), which ChatThread renders full width rather than as a
 * bubble, so this component only handles text.
 *
 * Only the person gets a bubble. Two columns of tinted bubbles is the
 * look every chat UI defaults to, and it makes the assistant's reply
 * read as a second participant in a conversation rather than as the
 * app answering. Plain text with a small mark beside it is quieter and
 * leaves the bubbles meaning one thing: this is what you said.
 */
export function ChatMessage({ role, body, time }) {
  const isUser = role === 'user';

  if (isUser) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Box
          sx={(theme) => ({
            px: 2,
            py: 1.5,
            maxWidth: '85%',
            borderRadius: 2.5,
            fontWeight: 600,
            color: theme.vars.palette.common.white,
            bgcolor: theme.vars.palette.text.primary,
            borderBottomRightRadius: theme.spacing(0.75),
          })}
        >
          {/* 16px minimum body text per FR17, and `pre-wrap` so a
              multi-line message keeps the shape it was typed in. */}
          <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {body}
          </Typography>

          {time && (
            <Typography
              variant="caption"
              component="time"
              sx={{ mt: 0.5, display: 'block', opacity: 0.56 }}
            >
              {time}
            </Typography>
          )}
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ gap: 1.25, display: 'flex', alignItems: 'flex-start' }}>
      <AssistantMark />

      <Box sx={{ flexGrow: 1, minWidth: 0, maxWidth: '85%' }}>
        <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
          {body}
        </Typography>

        {time && (
          <Typography
            variant="caption"
            component="time"
            sx={{ mt: 0.5, display: 'block', color: 'text.disabled' }}
          >
            {time}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

// ----------------------------------------------------------------------

/**
 * The dot that marks a machine turn.
 *
 * Same shape as the bubble in the logo, which is the whole idea: one
 * mark, used wherever the app speaks for itself.
 */
export function AssistantMark() {
  return (
    <Box
      aria-hidden
      sx={(theme) => ({
        mt: 0.5,
        width: 26,
        height: 26,
        flexShrink: 0,
        display: 'flex',
        borderRadius: '50%',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: theme.vars.palette.primary.lighter,
      })}
    >
      <Box
        sx={(theme) => ({
          width: 9,
          height: 9,
          borderRadius: '50%',
          bgcolor: theme.vars.palette.primary.main,
        })}
      />
    </Box>
  );
}
