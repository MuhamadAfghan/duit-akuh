'use client';

import { mergeClasses } from 'minimal-shared/utils';

import Link from '@mui/material/Link';
import { styled, useTheme } from '@mui/material/styles';

import { RouterLink } from 'src/routes/components';

import { logoClasses } from './classes';

// ----------------------------------------------------------------------

export function Logo({ sx, disabled, className, href = '/', isSingle = true, ...other }) {
  const theme = useTheme();

  const TEXT_PRIMARY = theme.vars.palette.text.primary;
  const PRIMARY_MAIN = theme.vars.palette.primary.main;
  const CONTRAST = theme.vars.palette.primary.contrastText;

  /*
    * OR using local (public folder)
    *
    /**
   * A spirit level: a flat line with the bubble dead centre.
   *
   * It stands for the rule the ledger rests on — every transaction is
   * recorded on two sides and has to sum to exactly zero — and for what
   * that buys the person using it. The dot is the same mark that stands
   * beside the assistant's turns in chat and ends the wordmark.
   *
   * No gradients. The mark has to survive being 16 pixels wide in a
   * browser tab and one colour on a receipt.
   */
  const singleLogo = (
    <svg
      width="100%"
      height="100%"
      viewBox="0 0 120 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="120" height="120" rx="34" fill={PRIMARY_MAIN} />
      <path d="M22 60 H42" stroke={CONTRAST} strokeWidth="9" strokeLinecap="round" />
      <path d="M78 60 H98" stroke={CONTRAST} strokeWidth="9" strokeLinecap="round" />
      <circle cx="60" cy="60" r="13" fill={CONTRAST} />
    </svg>
  );

  const fullLogo = (
    <svg
      width="100%"
      height="100%"
      viewBox="0 0 320 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="120" height="120" rx="34" fill={PRIMARY_MAIN} />
      <path d="M22 60 H42" stroke={CONTRAST} strokeWidth="9" strokeLinecap="round" />
      <path d="M78 60 H98" stroke={CONTRAST} strokeWidth="9" strokeLinecap="round" />
      <circle cx="60" cy="60" r="13" fill={CONTRAST} />

      <text
        x="146"
        y="84"
        fill={TEXT_PRIMARY}
        fontFamily="'Plus Jakarta Sans Variable', system-ui, sans-serif"
        fontSize="76"
        fontWeight="800"
        letterSpacing="-3"
      >
        lega
        <tspan fill={PRIMARY_MAIN}>.</tspan>
      </text>
    </svg>
  );

  return (
    <LogoRoot
      component={RouterLink}
      href={href}
      aria-label="Logo"
      underline="none"
      className={mergeClasses([logoClasses.root, className])}
      sx={[
        {
          width: 40,
          height: 40,
          ...(!isSingle && { width: 107, height: 40 }),
          ...(disabled && { pointerEvents: 'none' }),
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
      {...other}
    >
      {isSingle ? singleLogo : fullLogo}
    </LogoRoot>
  );
}

// ----------------------------------------------------------------------

const LogoRoot = styled(Link)(() => ({
  flexShrink: 0,
  color: 'transparent',
  display: 'inline-flex',
  verticalAlign: 'middle',
}));
