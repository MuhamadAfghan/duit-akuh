import { CONFIG } from 'src/global-config';

import { ChatView } from 'src/sections/chat/view';

// ----------------------------------------------------------------------

export const metadata = { title: CONFIG.appName };

/**
 * Chat is the root route, not a sub-page: the PRD makes one persistent
 * conversation the centre of the app (FR14).
 */
export default function Page() {
  return <ChatView />;
}
