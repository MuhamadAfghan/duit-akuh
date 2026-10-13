'use client';

import Box from '@mui/material/Box';

import { paths } from 'src/routes/paths';
import { usePathname } from 'src/routes/hooks';

import { useVirtualKeyboard } from 'src/hooks';

import { BottomTabs } from './bottom-tabs';
import { APP_COLUMN_WIDTH } from './column';

// ----------------------------------------------------------------------

/**
 * Mobile-first app shell (PRD section 12).
 *
 * Fills exactly the dynamic viewport and never scrolls as a page — only the
 * content area scrolls. That is what keeps the chat composer pinned above
 * the keyboard and prevents the horizontal/vertical page scrolling the PRD
 * forbids at 320-430 CSS px.
 *
 * On wide screens the column is centred and capped rather than stretched,
 * because the layout is designed one-handed first; desktop is supported,
 * not optimised for.
 */
export function AppShell({ children }) {
  const pathname = usePathname();
  const { keyboardInset, isKeyboardOpen } = useVirtualKeyboard();

  /**
   * The chat gets the whole column.
   *
   * It is the only surface with a composer, so it is the only one where
   * a floating bar competes with the keyboard for the bottom of the
   * screen — and the only one whose content is a conversation you scroll
   * rather than a page you read. It carries its own menu in the header
   * instead (`AppMenuButton`). Every other surface keeps the bar.
   */
  const showTabs = pathname !== paths.chat;

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'center',
        height: '100dvh',
        // Older iOS Safari lacks dvh; vh is a close-enough fallback that the
        // keyboard inset below then corrects.
        minHeight: '100vh',
        overflow: 'hidden',
      }}
    >
      <Box
        sx={(theme) => ({
          width: 1,
          maxWidth: APP_COLUMN_WIDTH,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          // The canvas every surface sits on. White belongs to cards, not
          // to the page: it is what makes a rounded card read as raised.
          bgcolor: theme.vars.palette.grey[100],
          // Compress by the keyboard's height so the composer stays visible.
          paddingBottom: keyboardInset ? `${keyboardInset}px` : 0,
          [theme.breakpoints.up('sm')]: {
            borderInline: `solid 1px ${theme.vars.palette.divider}`,
          },
        })}
      >
        <Box
          component="main"
          sx={{
            flex: '1 1 auto',
            // Without an explicit zero min-height a flex child refuses to
            // shrink, so the inner scroll area would push the tabs off-screen.
            minHeight: 0,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {children}
        </Box>

        {showTabs && <BottomTabs hidden={isKeyboardOpen} />}
      </Box>
    </Box>
  );
}
