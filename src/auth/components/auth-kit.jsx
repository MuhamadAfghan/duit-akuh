'use client';

import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';

import { RouterLink } from 'src/routes/components';

import { Iconify } from 'src/components/iconify';
import { Field } from 'src/components/hook-form';

// ----------------------------------------------------------------------

/**
 * The auth screens, as the boards draw them.
 *
 * They are deliberately not the template's split layout with a
 * marketing panel: phone is the primary device, and the first thing
 * somebody sees should be the same surface as the rest of the app, not
 * a desktop brochure that collapses awkwardly.
 */

/** The spirit level, at the size the boards use above a title. */
export function AuthMark() {
  return (
    <Box
      aria-hidden
      sx={{
        width: 56,
        height: 56,
        display: 'grid',
        borderRadius: 2.25,
        placeItems: 'center',
        color: 'primary.contrastText',
        bgcolor: 'primary.main',
      }}
    >
      <Box component="svg" width={32} height={32} viewBox="0 0 120 120" sx={{ display: 'block' }}>
        <path d="M22 60 H42" stroke="currentColor" strokeWidth="9" strokeLinecap="round" />
        <path d="M78 60 H98" stroke="currentColor" strokeWidth="9" strokeLinecap="round" />
        <circle cx="60" cy="60" r="13" fill="currentColor" />
      </Box>
    </Box>
  );
}

export function AuthHead({ mark, icon, title, description }) {
  return (
    <>
      {mark && <AuthMark />}
      {icon}

      <Typography
        component="h1"
        sx={{
          mt: mark || icon ? 3 : 0,
          fontSize: 34,
          lineHeight: '40px',
          fontWeight: 800,
          letterSpacing: '-0.03em',
        }}
      >
        {title}
      </Typography>

      {description && (
        <Typography
          sx={{ mt: 1, fontSize: 16, lineHeight: '24px', fontWeight: 600, color: 'text.secondary' }}
        >
          {description}
        </Typography>
      )}
    </>
  );
}

/** A 56px filled field with its label in caps above it. */
export function AuthField({ name, label, helper, ...other }) {
  return (
    <Box>
      <Typography
        component="label"
        htmlFor={name}
        sx={{
          display: 'block',
          fontSize: 12,
          fontWeight: 800,
          letterSpacing: '0.04em',
          color: 'text.secondary',
        }}
      >
        {label}
      </Typography>

      <Field.Text
        name={name}
        id={name}
        fullWidth
        sx={{
          mt: 1,
          '& .MuiOutlinedInput-root': {
            height: 56,
            borderRadius: 2,
            fontSize: 16,
            fontWeight: 600,
            bgcolor: 'grey.100',
            '& fieldset': { border: 'none' },
            '&.Mui-focused': {
              boxShadow: (theme) => `inset 0 0 0 2px ${theme.vars.palette.grey[300]}`,
            },
            '&.Mui-error': {
              boxShadow: (theme) => `inset 0 0 0 2px ${theme.vars.palette.error.main}`,
            },
          },
        }}
        {...other}
      />

      {helper && (
        <Typography
          sx={{ mt: 1, fontSize: 12, lineHeight: 1.5, fontWeight: 600, color: 'text.secondary' }}
        >
          {helper}
        </Typography>
      )}
    </Box>
  );
}

/** The black pill that carries the screen's one action. */
export function AuthSubmit({
  children,
  loading,
  loadingIndicator,
  onClick,
  href,
  type = 'submit',
}) {
  return (
    <Button
      fullWidth
      type={href ? undefined : type}
      onClick={onClick}
      loading={loading}
      loadingIndicator={loadingIndicator}
      {...(href ? { component: RouterLink, href } : {})}
      sx={{
        height: 56,
        fontSize: 16,
        fontWeight: 800,
        borderRadius: 999,
        color: 'common.white',
        bgcolor: 'grey.800',
        '&:hover': { bgcolor: 'grey.700' },
      }}
    >
      {children}
    </Button>
  );
}

/** Quiet block for the reasoning the boards put under the form. */
export function AuthNote({ icon, title, children, tone = 'plain' }) {
  const tones = {
    plain: { bg: 'grey.100', fg: 'grey.700', badge: 'common.white', badgeFg: 'grey.700' },
    good: {
      bg: 'primary.lighter',
      fg: 'primary.darker',
      badge: 'primary.main',
      badgeFg: 'common.white',
    },
    warn: { bg: '#FFFBEB', fg: '#6B4F00', badge: '#FFE55C', badgeFg: '#6B4F00' },
    bad: { bg: '#FDF0F0', fg: '#8E1212', badge: '#C01818', badgeFg: '#FFFFFF' },
  };
  const tone_ = tones[tone] ?? tones.plain;

  return (
    <Stack direction="row" sx={{ p: 2, gap: 1.5, borderRadius: 2, bgcolor: tone_.bg }}>
      {icon && (
        <Box
          sx={{
            width: 26,
            height: 26,
            flexShrink: 0,
            display: 'grid',
            placeItems: 'center',
            borderRadius: '50%',
            color: tone_.badgeFg,
            bgcolor: tone_.badge,
          }}
        >
          <Iconify icon={icon} width={15} />
        </Box>
      )}

      <Box sx={{ color: tone_.fg }}>
        {title && <Box sx={{ fontSize: 14, fontWeight: 800 }}>{title}</Box>}
        <Box sx={{ mt: title ? 0.75 : 0, fontSize: 13, lineHeight: '20px', fontWeight: 600 }}>
          {children}
        </Box>
      </Box>
    </Stack>
  );
}

/** The one line at the bottom of every auth screen. */
export function AuthFooter({ prompt, label, href }) {
  return (
    <Box
      sx={{
        flexShrink: 0,
        pt: 1.5,
        pb: 'calc(env(safe-area-inset-bottom) + 28px)',
        textAlign: 'center',
      }}
    >
      {prompt && (
        <Box component="span" sx={{ fontSize: 15, fontWeight: 600, color: 'text.secondary' }}>
          {`${prompt} `}
        </Box>
      )}
      <Link
        component={RouterLink}
        href={href}
        sx={{ fontSize: 15, fontWeight: 800, color: 'primary.dark' }}
      >
        {label}
      </Link>
    </Box>
  );
}
