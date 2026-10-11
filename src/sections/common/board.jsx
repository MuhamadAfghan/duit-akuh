'use client';

import { useState } from 'react';

import Box from '@mui/material/Box';
import Menu from '@mui/material/Menu';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import { visuallyHidden } from '@mui/utils';
import Skeleton from '@mui/material/Skeleton';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import IconButton from '@mui/material/IconButton';

import { RouterLink } from 'src/routes/components';

import { formatRupiah, formatRupiahPlain } from 'src/utils/format-money';

import { Iconify } from 'src/components/iconify';

// ----------------------------------------------------------------------

/**
 * The pieces every surface is built from, lifted straight off the
 * approved design boards.
 *
 * They exist so a screen is a list of these rather than a pile of
 * hexes and paddings: when the boards change, this file changes, and
 * nine screens follow. Numbers that look arbitrary here — the 24px
 * hero radius, the 74px divider inset, the 44px avatar — are the
 * board's, not improvisations.
 */

// ----------------------------------------------------------------------

/** Page title row. 26px/800 on the canvas, not on a white bar. */
export function BoardTitle({ title, backHref, action }) {
  return (
    <Box
      component="header"
      sx={{
        flexShrink: 0,
        px: backHref ? 0.5 : 2,
        pt: 'calc(env(safe-area-inset-top) + 14px)',
        pb: 1.25,
        gap: 1.5,
        display: 'flex',
        alignItems: 'center',
      }}
    >
      {backHref && (
        <IconButton
          component={RouterLink}
          href={backHref}
          aria-label="Kembali"
          sx={{ width: 44, height: 44, color: 'text.primary' }}
        >
          <Iconify icon="lega:back" width={22} />
        </IconButton>
      )}

      <Typography
        component="h1"
        sx={{
          flexGrow: 1,
          minWidth: 0,
          fontSize: backHref ? 22 : 26,
          fontWeight: 800,
          letterSpacing: '-0.03em',
        }}
      >
        {title}
      </Typography>

      {action}
    </Box>
  );
}

/** The round white button that sits beside a title. */
export function BoardAction({ icon, label, onClick, href }) {
  return (
    <IconButton
      aria-label={label}
      onClick={onClick}
      {...(href ? { component: RouterLink, href } : {})}
      sx={{ width: 44, height: 44, bgcolor: 'common.white', color: 'text.primary' }}
    >
      <Iconify icon={icon} width={22} />
    </IconButton>
  );
}

/** Scrolling body. Everything below the title lives in here. */
export function BoardBody({ children, sx }) {
  return (
    <Box
      sx={[
        {
          flex: '1 1 auto',
          minHeight: 0,
          overflowY: 'auto',
          px: 2,
          // No safe-area inset here: every surface that uses BoardBody
          // still has the floating tab bar under it, and the bar carries
          // its own `env(safe-area-inset-bottom)` margin. The chat is the
          // exception, and its composer does this for itself.
          pb: 2,
          gap: 2,
          display: 'flex',
          flexDirection: 'column',
          // A flex child shrinks by default, so inside a scrolling
          // column every card gets squeezed to fit and then clips its
          // own content behind overflow:hidden. Cards must keep their
          // natural height and let the column scroll instead.
          '& > *': { flexShrink: 0 },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {children}
    </Box>
  );
}

// ----------------------------------------------------------------------

/**
 * Placeholders shaped like the thing that is coming.
 *
 * A skeleton is only worth more than a spinner if it occupies the same
 * space as the real content: otherwise it is a prettier spinner that
 * also shifts the layout when the data lands, and the PRD asks the
 * chat shell to hold CLS at 0.1 or under. So these mirror the cards
 * above them — same radii, same paddings, same row height — and each
 * screen composes its own out of them rather than sharing one generic
 * blob.
 *
 * They are `aria-hidden` and the surface says it is loading once, out
 * loud. Six announced grey rectangles are noise to a screen reader.
 */

/** The wave, unless the person asked for less motion (FR18). */
const skeletonSx = {
  '@media (prefers-reduced-motion: reduce)': { '&::after': { animation: 'none' } },
};

/** One line of text-shaped grey. `w` is a percentage or a number. */
export function SkeletonLine({ w = '100%', h = 14, sx }) {
  return (
    <Skeleton
      variant="rounded"
      animation="wave"
      width={w}
      height={h}
      sx={[skeletonSx, { borderRadius: 1 }, ...(Array.isArray(sx) ? sx : [sx])]}
    />
  );
}

/**
 * The dark hero, before its number arrives.
 *
 * Dark on purpose: the real one is `grey.800`, and flashing a white
 * card that turns black is worse than a moment of grey.
 */
export function SkeletonHero({ children }) {
  return (
    <Card aria-hidden sx={{ p: 2.5, borderRadius: 3, bgcolor: 'grey.800' }}>
      <SkeletonLine w={140} h={13} sx={{ bgcolor: 'grey.700' }} />
      <SkeletonLine w={210} h={38} sx={{ mt: 1, bgcolor: 'grey.700' }} />
      {children}
    </Card>
  );
}

/** Two tiles, the width and height of the real pair. */
export function SkeletonTiles() {
  return (
    <Box
      aria-hidden
      sx={{ gap: 1.5, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}
    >
      {[0, 1].map((slot) => (
        <Box key={slot} sx={{ p: 2, borderRadius: 2.5, bgcolor: 'common.white' }}>
          <SkeletonLine w="70%" h={12} />
          <SkeletonLine w="55%" h={20} sx={{ mt: 1 }} />
        </Box>
      ))}
    </Box>
  );
}

/**
 * A list card with `rows` placeholder rows.
 *
 * The 74px avatar column and the hairline inset match `RowDivider`, so
 * the real rows drop into exactly these positions.
 */
export function SkeletonRows({ rows = 3 }) {
  return (
    <Card aria-hidden sx={{ borderRadius: 2.5, overflow: 'hidden' }}>
      {Array.from({ length: rows }, (unused, index) => (
        <Box key={index}>
          {index > 0 && <Box sx={{ height: '1px', ml: '74px', bgcolor: 'grey.200' }} />}

          <Stack direction="row" sx={{ px: 2, py: 1.75, gap: 1.5, alignItems: 'center' }}>
            <Skeleton
              variant="circular"
              animation="wave"
              width={44}
              height={44}
              sx={[skeletonSx, { flexShrink: 0 }]}
            />

            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <SkeletonLine w={`${55 + ((index * 13) % 30)}%`} h={15} />
              <SkeletonLine w={`${34 + ((index * 17) % 24)}%`} h={12} sx={{ mt: 0.75 }} />
            </Box>

            <SkeletonLine w={74} h={15} />
          </Stack>
        </Box>
      ))}
    </Card>
  );
}

/**
 * Wraps a screen's placeholders and says "loading" once.
 *
 * The skeletons themselves are `aria-hidden`: six announced grey
 * rectangles are noise, and the one thing worth saying is that the
 * screen is working on it.
 */
export function Loading({ label = 'Memuat…', children }) {
  return (
    <>
      <Box role="status" aria-live="polite" sx={visuallyHidden}>
        {label}
      </Box>

      {children}
    </>
  );
}

/** A plain card of a given height, for sections with their own shape. */
export function SkeletonCard({ height = 120 }) {
  return (
    <Skeleton
      aria-hidden
      variant="rounded"
      animation="wave"
      height={height}
      sx={[skeletonSx, { borderRadius: 2.5 }]}
    />
  );
}

// ----------------------------------------------------------------------

/** The dark card that carries the one number a screen is about. */
export function HeroCard({ label, amount, caption, children }) {
  return (
    <Card sx={{ p: 2.5, borderRadius: 3, bgcolor: 'grey.800', color: 'common.white' }}>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.500' }}>{label}</Typography>

      <Money amount={amount} sx={{ mt: 0.25, fontSize: 36, lineHeight: '44px', fontWeight: 800 }} />

      {children}

      {caption && (
        <Typography
          sx={{ mt: 1.5, fontSize: 12, lineHeight: 1.5, fontWeight: 600, color: 'grey.500' }}
        >
          {caption}
        </Typography>
      )}
    </Card>
  );
}

/** Circular shortcut inside a hero card. */
export function QuickAction({ icon, label, href }) {
  return (
    <Stack
      component={RouterLink}
      href={href}
      sx={{ gap: 0.9, minHeight: 48, alignItems: 'center', textDecoration: 'none' }}
    >
      <Box
        sx={{
          width: 48,
          height: 48,
          display: 'grid',
          placeItems: 'center',
          borderRadius: '50%',
          color: 'common.white',
          bgcolor: 'rgba(255,255,255,0.1)',
        }}
      >
        <Iconify icon={icon} width={22} />
      </Box>
      <Box component="span" sx={{ fontSize: 11, fontWeight: 700, color: 'grey.300' }}>
        {label}
      </Box>
    </Stack>
  );
}

/** Two tinted figures side by side, under a hero. */
export function StatTile({ label, amount, tone = 'good' }) {
  const tones = {
    good: { bg: 'primary.lighter', label: 'primary.dark', value: 'primary.darker' },
    bad: { bg: 'error.lighter', label: 'error.dark', value: 'error.darker' },
    plain: { bg: 'common.white', label: 'text.secondary', value: 'text.primary' },
  };
  const tone_ = tones[tone] ?? tones.plain;

  return (
    <Box sx={{ p: 2, borderRadius: 2.5, bgcolor: tone_.bg }}>
      <Typography sx={{ fontSize: 12, fontWeight: 700, color: tone_.label }}>{label}</Typography>
      <Money
        amount={amount}
        plain
        sx={{ mt: 0.5, fontSize: 20, fontWeight: 800, color: tone_.value }}
      />
    </Box>
  );
}

export function TileRow({ children }) {
  return (
    <Box sx={{ gap: 1.5, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
      {children}
    </Box>
  );
}

// ----------------------------------------------------------------------

export function SectionLabel({ children }) {
  return (
    <Typography
      component="h2"
      sx={{
        ml: 0.5,
        mb: -0.75,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: '0.06em',
        color: 'text.secondary',
      }}
    >
      {children}
    </Typography>
  );
}

/** White rounded block holding rows. */
export function ListCard({ children, sx }) {
  return (
    <Card sx={[{ borderRadius: 2.5, overflow: 'hidden' }, ...(Array.isArray(sx) ? sx : [sx])]}>
      {children}
    </Card>
  );
}

/** Hairline between rows, inset past the avatar so the column reads. */
export function RowDivider() {
  return <Box sx={{ height: '1px', ml: '74px', bgcolor: 'grey.200' }} />;
}

/**
 * One row: avatar, name over a note, and a figure on the right.
 * `href` makes the whole row the tap target rather than a link inside it.
 *
 * `external` swaps the router link for a plain anchor. A file download
 * is not a route: handing /srv/export/transactions.csv to the router
 * means a client navigation to something that answers with a
 * Content-Disposition header, so the browser has to do it.
 */
export function ListRow({
  avatar,
  title,
  note,
  value,
  valueTone,
  href,
  external,
  onClick,
  action,
}) {
  const interactive = Boolean(href || onClick);
  const linkProps = href ? { href, component: external ? 'a' : RouterLink } : {};

  return (
    <Stack
      direction="row"
      {...linkProps}
      {...(onClick ? { component: 'button', type: 'button', onClick } : {})}
      sx={{
        px: 2,
        py: 1.75,
        gap: 1.75,
        width: 1,
        border: 'none',
        minHeight: 48,
        textAlign: 'left',
        alignItems: 'center',
        bgcolor: 'transparent',
        textDecoration: 'none',
        color: 'text.primary',
        ...(interactive && { cursor: 'pointer' }),
      }}
    >
      {avatar}

      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Typography noWrap sx={{ fontSize: 15, fontWeight: 700 }}>
          {title}
        </Typography>
        {note && (
          <Typography sx={{ fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
            {note}
          </Typography>
        )}
      </Box>

      {value != null && (
        <Money
          amount={value}
          plain={false}
          tone={valueTone}
          sx={{ fontSize: 16, fontWeight: 800 }}
        />
      )}

      {action}
    </Stack>
  );
}

/** Round badge carrying initials or a glyph. */
export function RowAvatar({ children, icon, tone = 'blue' }) {
  const tones = {
    blue: { bg: '#DEF5FC', fg: '#00627C' },
    amber: { bg: '#FFF0DC', fg: '#7A4A00' },
    green: { bg: 'primary.lighter', fg: 'primary.dark' },
    grey: { bg: 'grey.100', fg: 'grey.700' },
    ink: { bg: 'grey.800', fg: 'common.white' },
    red: { bg: 'error.lighter', fg: 'error.dark' },
  };
  const tone_ = tones[tone] ?? tones.grey;

  return (
    <Box
      sx={{
        width: 44,
        height: 44,
        flexShrink: 0,
        display: 'grid',
        fontSize: 13,
        fontWeight: 800,
        placeItems: 'center',
        borderRadius: '50%',
        color: tone_.fg,
        bgcolor: tone_.bg,
      }}
    >
      {icon ? <Iconify icon={icon} width={21} /> : children}
    </Box>
  );
}

// ----------------------------------------------------------------------

/**
 * Money, always with tabular figures so columns of amounts line up.
 * `plain` drops the Rp prefix where the label already carries the unit.
 */
export function Money({ amount, plain = false, signed = false, tone, sx }) {
  const text = plain ? formatRupiahPlain(amount) : formatRupiah(amount, { signed });

  const tones = { good: 'primary.dark', bad: 'error.dark', muted: 'text.secondary' };

  return (
    <Box
      component="span"
      sx={[
        { display: 'block', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' },
        tone ? { color: tones[tone] } : null,
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {text}
    </Box>
  );
}

/** Progress bar at the board's weight, with its own track colour. */
export function Bar({ value, tone = 'good', height = 10 }) {
  const fills = { good: 'primary.main', warn: '#C79000', bad: 'error.main', ink: 'grey.800' };

  return (
    <Box sx={{ height, borderRadius: 999, bgcolor: 'grey.200', overflow: 'hidden' }}>
      <Box
        sx={{
          height: 1,
          borderRadius: 999,
          width: `${Math.min(Math.max(value, 0), 100)}%`,
          bgcolor: fills[tone] ?? fills.good,
        }}
      />
    </Box>
  );
}

/**
 * The progress ring from the Target board.
 *
 * Capped at 100: a ring past full says nothing, and any excess is
 * reported separately as surplus (FR07). The figure is drawn inside
 * rather than beside it, so the shape is never the only signal.
 */
export function Ring({ percent, tone = 'good', size = 64 }) {
  const colours = { good: '#009A5B', warn: '#C79000', muted: '#8A9298' };
  const radius = 26;
  const stroke = 8;
  const circumference = 2 * Math.PI * radius;
  const filled = (Math.min(Math.max(percent, 0), 100) / 100) * circumference;

  // A round cap adds half the stroke width beyond each end, so an arc
  // drawn at its true length renders one stroke longer than it should.
  // At 33% nobody notices; at 9% the ring reads as a blob twice the
  // progress it means. Draw the dash short by that overhang, and give
  // up the caps entirely once there is nothing left to trim.
  const capped = filled > stroke;
  const dash = capped ? filled - stroke : filled;

  return (
    <Box
      component="svg"
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label={`Terkumpul ${percent} persen`}
      sx={{ flexShrink: 0 }}
    >
      <circle cx="32" cy="32" r={radius} fill="none" stroke="#EEEFF0" strokeWidth={stroke} />
      {filled > 0 && (
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={colours[tone] ?? colours.good}
          strokeWidth={stroke}
          strokeLinecap={capped ? 'round' : 'butt'}
          strokeDasharray={`${dash} ${circumference}`}
          transform="rotate(-90 32 32)"
        />
      )}
      <text x="32" y="37" textAnchor="middle" fontSize="16" fontWeight="800" fill="#0B0D0E">
        {percent}%
      </text>
    </Box>
  );
}

/** The small caps badge the boards use for state. */
export function Pill({ children, tone = 'warn' }) {
  const tones = {
    warn: { bg: '#FFE55C', fg: '#6B4F00' },
    bad: { bg: 'error.main', fg: 'common.white' },
    good: { bg: 'primary.lighter', fg: 'primary.darker' },
    info: { bg: '#DEF5FC', fg: '#00465A' },
  };
  const tone_ = tones[tone] ?? tones.warn;

  return (
    <Box
      component="span"
      sx={{
        px: 1,
        py: 0.4,
        fontSize: 10,
        fontWeight: 800,
        borderRadius: 999,
        letterSpacing: '0.04em',
        color: tone_.fg,
        bgcolor: tone_.bg,
      }}
    >
      {children}
    </Box>
  );
}

/**
 * A filter pill that opens its own options.
 *
 * The selected value is the label, so the row of chips reads as the
 * current question rather than as a set of buttons you have to open to
 * find out what they are set to.
 */
export function FilterChip({ value, options, onChange }) {
  const [anchor, setAnchor] = useState(null);

  const current = options.find((option) => option.value === value) ?? options[0];
  const isDefault = current?.value === options[0]?.value;

  return (
    <>
      <Box
        component="button"
        type="button"
        onClick={(event) => setAnchor(event.currentTarget)}
        sx={{
          px: 1.75,
          gap: 0.5,
          height: 36,
          display: 'flex',
          flexShrink: 0,
          fontSize: 13,
          cursor: 'pointer',
          alignItems: 'center',
          borderRadius: 999,
          border: 'none',
          fontWeight: isDefault ? 700 : 800,
          color: isDefault ? 'text.primary' : 'common.white',
          bgcolor: isDefault ? 'common.white' : 'grey.800',
        }}
      >
        {current?.label}
        <Iconify icon="eva:arrow-ios-downward-fill" width={15} />
      </Box>

      <Menu
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        slotProps={{ paper: { sx: { borderRadius: 2, minWidth: 180 } } }}
      >
        {options.map((option) => (
          <MenuItem
            key={option.value ?? 'all'}
            selected={option.value === value}
            onClick={() => {
              onChange(option.value);
              setAnchor(null);
            }}
            sx={{ minHeight: 44, fontSize: 14, fontWeight: 700 }}
          >
            {option.label}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
}

/** Quiet explanatory block. Carries the rules the product will not bend. */
export function BoardNote({ children, tone = 'plain' }) {
  const tones = {
    plain: { bg: 'grey.100', fg: 'grey.700' },
    warn: { bg: '#FFFBEB', fg: '#6B4F00' },
    info: { bg: '#DEF5FC', fg: '#00465A' },
    bad: { bg: '#FDF0F0', fg: '#8E1212' },
  };
  const tone_ = tones[tone] ?? tones.plain;

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 1.75,
        fontSize: 12,
        lineHeight: 1.55,
        fontWeight: 600,
        color: tone_.fg,
        bgcolor: tone_.bg,
      }}
    >
      {children}
    </Box>
  );
}

// ----------------------------------------------------------------------

/** The wallet colour each account type gets, everywhere it appears. */
export const WALLET_TONES = {
  bank: 'blue',
  ewallet: 'green',
  cash: 'amber',
  credit_card: 'ink',
};

/**
 * Up to three letters for an avatar: initials for a multi-word name,
 * otherwise the first letters of the one word. "Bank Central Asia" is
 * BCA; "Gopay" is GOP.
 */
export function walletInitials(name) {
  const words = name.trim().split(/\s+/);

  return (
    words.length > 1
      ? words
          .slice(0, 3)
          .map((word) => word[0])
          .join('')
      : name.slice(0, 3)
  ).toUpperCase();
}

/**
 * A horizontal row of wallets to choose from, the way the boards draw
 * it: the avatar, a ring when chosen, the name under it.
 *
 * Scrolls sideways on purpose. A dropdown hides which wallets exist,
 * and on a phone the whole point is seeing them.
 */
export function WalletPicker({ accounts, selectedId, onSelect, label }) {
  return (
    <Stack
      direction="row"
      role="group"
      aria-label={label}
      sx={{ gap: 1.75, overflowX: 'auto', pb: 0.5 }}
    >
      {accounts.map((account) => {
        const active = account.id === selectedId;

        return (
          <Stack
            key={account.id}
            component="button"
            type="button"
            aria-pressed={active}
            aria-label={account.name}
            onClick={() => onSelect(account.id)}
            sx={{
              p: 0,
              gap: 0.75,
              width: 60,
              border: 'none',
              flexShrink: 0,
              cursor: 'pointer',
              alignItems: 'center',
              bgcolor: 'transparent',
            }}
          >
            <Box
              aria-hidden
              sx={{
                borderRadius: '50%',
                boxShadow: active ? '0 0 0 3px' : 'none',
                color: 'primary.main',
              }}
            >
              <RowAvatar tone={WALLET_TONES[account.type]}>
                {walletInitials(account.name)}
              </RowAvatar>
            </Box>
            <Box
              component="span"
              aria-hidden
              sx={{
                maxWidth: 1,
                fontSize: 11,
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
                fontWeight: active ? 800 : 700,
                color: active ? 'text.primary' : 'text.secondary',
              }}
            >
              {account.name}
            </Box>
          </Stack>
        );
      })}
    </Stack>
  );
}

// ----------------------------------------------------------------------

/**
 * Appends a keypad press to a digit string.
 *
 * Nine digits is a hundred million rupiah; past that it is a typo, so
 * the string stops growing rather than silently accepting a figure
 * nobody meant to type.
 */
export function pressDigit(current, key) {
  if (key === 'back') {
    return current.slice(0, -1);
  }

  return `${current}${key}`.replace(/^0+/, '').slice(0, 9);
}

/**
 * The on-screen keypad from the Entri-Manual board.
 *
 * It exists instead of a number field because this is a phone: the
 * native keyboard would cover the impact lines the person is supposed
 * to read before committing, and `000` saves three taps on every
 * rupiah figure.
 */
export function AmountKeypad({ onPress }) {
  return (
    <Box sx={{ gap: 0.75, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
      {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((key) => (
        <Key key={key} onClick={() => onPress(key)}>
          {key}
        </Key>
      ))}
      <Key muted onClick={() => onPress('000')}>
        000
      </Key>
      <Key onClick={() => onPress('0')}>0</Key>
      <Key muted label="Hapus satu angka" onClick={() => onPress('back')}>
        <Iconify icon="mingcute:close-line" width={20} />
      </Key>
    </Box>
  );
}

function Key({ children, onClick, muted, label }) {
  return (
    <Button
      onClick={onClick}
      aria-label={label}
      sx={{
        minHeight: 46,
        fontSize: 20,
        fontWeight: 700,
        borderRadius: 1.5,
        color: muted ? 'text.secondary' : 'text.primary',
        bgcolor: muted ? 'transparent' : 'grey.100',
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {children}
    </Button>
  );
}

/**
 * A tappable pill from the boards' preset and category rows. Pressed
 * state is `aria-pressed`, not colour alone, because the boards' own
 * rule is that nothing may be communicated by colour only.
 */
export function ChoiceChip({ label, active, onClick }) {
  return (
    <Box
      component="button"
      type="button"
      aria-pressed={active}
      onClick={onClick}
      sx={{
        px: 2,
        flexShrink: 0,
        minHeight: 40,
        fontSize: 14,
        cursor: 'pointer',
        fontWeight: active ? 800 : 700,
        borderRadius: 999,
        border: active ? 'none' : '1.5px solid',
        borderColor: 'grey.300',
        color: active ? 'common.white' : 'text.primary',
        bgcolor: active ? 'grey.800' : 'common.white',
      }}
    >
      {label}
    </Box>
  );
}
