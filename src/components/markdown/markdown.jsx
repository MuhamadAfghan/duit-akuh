'use client';

import { useMemo } from 'react';
import { varAlpha } from 'minimal-shared/utils';

import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Divider from '@mui/material/Divider';

import { parseInline, parseMarkdown } from './parse-markdown';

// ----------------------------------------------------------------------

/**
 * Markdown as the chat speaks it.
 *
 * Sized to inherit, not to impose: the bubble sets the type and this
 * only marks structure within it. A heading in a 430px bubble is one
 * step of weight, not a 32px display line — the model writes "### Ringkasan"
 * out of habit, and honouring that literally would shout.
 *
 * Reparsed on every streamed token, which is why `parseMarkdown` is a
 * plain function over a string: the memo below is the whole caching
 * story, and a reply is a few hundred characters.
 */
export function Markdown({ text, sx }) {
  const blocks = useMemo(() => parseMarkdown(text), [text]);

  return (
    <Box
      sx={[
        {
          typography: 'body1',
          fontWeight: 500,
          display: 'flex',
          flexDirection: 'column',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
          // The gap between blocks, owned here so nothing carries a
          // stray margin at the top or bottom of the bubble.
          //
          // A flex gap rather than `& > * + * { mt }`: the blocks set
          // their own `margin: 0`, and two emotion classes of equal
          // specificity are settled by insertion order, which the child
          // wins. The first draft of this looked right in the parser
          // tests and shipped with every block jammed together.
          gap: 1,
          // A flex item will not shrink below its content, so a wide
          // code block or table would push the bubble past the column
          // instead of scrolling inside it.
          '& > *': { minWidth: 0 },
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
    >
      {blocks.map((block, index) => (
        <Block key={index} block={block} />
      ))}
    </Box>
  );
}

// ----------------------------------------------------------------------

function Block({ block }) {
  switch (block.type) {
    case 'heading':
      return (
        <Box
          component={`h${Math.min(block.level + 2, 6)}`}
          sx={{
            m: 0,
            // A little air above, because a heading belongs to what
            // follows it rather than to what it interrupts.
            mt: 0.5,
            fontSize: block.level <= 2 ? '1.0625rem' : '1rem',
            fontWeight: 800,
            lineHeight: 1.4,
            '&:first-of-type': { mt: 0 },
          }}
        >
          <Inline nodes={parseInline(block.text)} />
        </Box>
      );

    case 'list':
      return (
        <Box
          component={block.ordered ? 'ol' : 'ul'}
          start={block.ordered ? block.start : undefined}
          sx={{
            m: 0,
            pl: block.ordered ? 2.75 : 2.25,
            // `global.css` resets every `ul` to `list-style-type: none`
            // for the nav menus, so a bullet has to be asked for by
            // name. Without this the list rendered as unindented
            // sentences and nothing looked like a list at all.
            listStyleType: block.ordered ? 'decimal' : 'disc',
            '& li + li': { mt: 0.5 },
            '& li::marker': {
              fontWeight: 700,
              color: block.ordered ? 'text.secondary' : 'primary.main',
            },
          }}
        >
          {block.items.map((item, index) => (
            <Box component="li" key={index} sx={{ pl: 0.25 }}>
              {/* The item's blocks are spaced by a wrapper rather than
                  by the `li`: a flex `li` is no longer `display: list-item`
                  and loses its marker. */}
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                {item.map((child, inner) => (
                  <Block key={inner} block={child} />
                ))}
              </Box>
            </Box>
          ))}
        </Box>
      );

    case 'quote':
      return (
        <Box
          component="blockquote"
          sx={(theme) => ({
            m: 0,
            pl: 1.5,
            color: theme.vars.palette.text.secondary,
            display: 'flex',
            flexDirection: 'column',
            gap: 0.75,
            borderLeft: `3px solid ${theme.vars.palette.primary.light}`,
          })}
        >
          {block.blocks.map((child, index) => (
            <Block key={index} block={child} />
          ))}
        </Box>
      );

    case 'code':
      return (
        <Box
          component="pre"
          sx={(theme) => ({
            m: 0,
            px: 1.5,
            py: 1.25,
            fontSize: 13,
            lineHeight: 1.6,
            overflowX: 'auto',
            borderRadius: 1.5,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            bgcolor: theme.vars.palette.grey[100],
            border: `solid 1px ${theme.vars.palette.divider}`,
            // Scrolls inside its own box, so the page never scrolls
            // sideways at 320px (FR17).
            WebkitOverflowScrolling: 'touch',
          })}
        >
          <Box component="code">{block.value}</Box>
        </Box>
      );

    case 'table':
      return <StackedTable header={block.header} rows={block.rows} />;

    case 'rule':
      return <Divider sx={{ borderStyle: 'dashed' }} />;

    default:
      return (
        <Box component="p" sx={{ m: 0 }}>
          <Inline nodes={parseInline(block.text)} />
        </Box>
      );
  }
}

// ----------------------------------------------------------------------

/**
 * A table, stacked.
 *
 * FR17 forbids a wide table in a phone column and FR18 asks for the
 * stacked detail instead, so each row becomes a small card of
 * label/value pairs. Four columns across 430px minus the bubble's own
 * padding is unreadable at any font size that is also >= 16px.
 */
function StackedTable({ header, rows }) {
  if (!rows.length) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      {rows.map((cells, index) => (
        <Box
          key={index}
          sx={(theme) => ({
            px: 1.5,
            py: 1,
            borderRadius: 1.5,
            bgcolor: theme.vars.palette.grey[100],
          })}
        >
          {cells.map((cell, column) => (
            <Box
              key={column}
              sx={{
                gap: 2,
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                '& + &': { mt: 0.5 },
              }}
            >
              {header[column] && (
                <Box
                  component="span"
                  sx={{ fontSize: 12, fontWeight: 700, color: 'text.secondary', flexShrink: 0 }}
                >
                  <Inline nodes={parseInline(header[column])} />
                </Box>
              )}

              <Box component="span" sx={{ fontSize: 14, fontWeight: 600, textAlign: 'right' }}>
                <Inline nodes={parseInline(cell)} />
              </Box>
            </Box>
          ))}
        </Box>
      ))}
    </Box>
  );
}

// ----------------------------------------------------------------------

function Inline({ nodes }) {
  return nodes.map((node, index) => <Span key={index} node={node} />);
}

function Span({ node }) {
  switch (node.type) {
    case 'break':
      return <br />;

    case 'strong':
      return (
        <Box component="strong" sx={{ fontWeight: 800 }}>
          <Inline nodes={node.children} />
        </Box>
      );

    case 'em':
      return (
        <Box component="em" sx={{ fontStyle: 'italic' }}>
          <Inline nodes={node.children} />
        </Box>
      );

    case 'strike':
      return (
        <Box component="s" sx={{ opacity: 0.7 }}>
          <Inline nodes={node.children} />
        </Box>
      );

    case 'code':
      return (
        <Box
          component="code"
          sx={(theme) => ({
            px: 0.625,
            py: 0.125,
            fontSize: '0.8125em',
            borderRadius: 0.75,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            bgcolor: varAlpha(theme.vars.palette.grey['500Channel'], 0.16),
          })}
        >
          {node.value}
        </Box>
      );

    case 'link':
      return (
        <Link
          href={node.href}
          target="_blank"
          rel="noopener noreferrer"
          sx={{ fontWeight: 700, color: 'primary.main', textDecorationColor: 'currentColor' }}
        >
          <Inline nodes={node.children} />
        </Link>
      );

    default:
      return node.value;
  }
}
