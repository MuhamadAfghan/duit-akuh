'use client';

import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import LinearProgress from '@mui/material/LinearProgress';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { formatRupiahPlain } from 'src/utils/format-money';

import { accountsApi } from 'src/lib/api';

import { WalletForm } from '../wallet-form';
import {
  Bar,
  Money,
  TileRow,
  ListRow,
  ListCard,
  StatTile,
  HeroCard,
  BoardBody,
  BoardNote,
  RowAvatar,
  BoardTitle,
  RowDivider,
  BoardAction,
  QuickAction,
  SectionLabel,
  SurfaceEmpty,
} from '../../common';

// ----------------------------------------------------------------------

const GROUPS = [
  { key: 'spend', label: 'REKENING & DOMPET', types: ['bank', 'ewallet', 'cash'] },
  { key: 'card', label: 'KARTU KREDIT', types: ['credit_card'] },
];

const TYPE_LABELS = {
  bank: 'Rekening',
  ewallet: 'E-wallet',
  cash: 'Tunai',
  credit_card: 'Kartu kredit',
};

const TONES = { bank: 'blue', ewallet: 'green', cash: 'amber', credit_card: 'ink' };

/** Up to three letters, so "Mandiri" reads as MDR rather than as a crop. */
function initials(name) {
  const words = name.trim().split(/\s+/);

  if (words.length > 1) {
    return words
      .slice(0, 3)
      .map((word) => word[0])
      .join('')
      .toUpperCase();
  }

  return name.slice(0, 3).toUpperCase();
}

// ----------------------------------------------------------------------

export function KantongView() {
  const [accounts, setAccounts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [formOpen, setFormOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rows, totals] = await Promise.all([accountsApi.list(), accountsApi.summary()]);
      setAccounts(rows);
      setSummary(totals);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const visible = accounts.filter((account) => !account.is_archived);

  return (
    <>
      <BoardTitle
        title="Kantong"
        action={
          <BoardAction icon="lega:plus" label="Tambah kantong" onClick={() => setFormOpen(true)} />
        }
      />

      {loading && <LinearProgress />}

      <BoardBody>
        {error && (
          <SurfaceEmpty
            icon="solar:danger-triangle-bold"
            title="Gagal memuat kantong"
            body={error}
          />
        )}

        {!error && !loading && visible.length === 0 && (
          <SurfaceEmpty
            icon="lega:wallet"
            title="Belum ada kantong"
            body="Tambah lewat tombol di atas, atau ketik di chat: “tambah kantong BCA saldo 5 juta”."
          />
        )}

        {!error && visible.length > 0 && summary && (
          <>
            <HeroCard label="Uang cair" amount={summary.liquid}>
              <Box
                sx={{
                  mt: 2,
                  gap: 1,
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
                }}
              >
                <QuickAction icon="lega:arrow-up" label="Top up" href={paths.catat} />
                <QuickAction icon="lega:swap" label="Pindah" href={paths.catat} />
                <QuickAction icon="lega:arrow-down" label="Tarik" href={paths.catat} />
                <QuickAction icon="lega:clock" label="Riwayat" href={paths.data} />
              </Box>
            </HeroCard>

            <TileRow>
              <StatTile label="Bebas pakai" amount={summary.free_to_spend} tone="good" />
              <StatTile label="Total utang" amount={summary.total_debt} tone="bad" />
            </TileRow>

            {GROUPS.map((group) => {
              const rows = visible.filter((account) => group.types.includes(account.type));

              if (!rows.length) {
                return null;
              }

              return (
                <Box key={group.key} sx={{ gap: 1.5, display: 'flex', flexDirection: 'column' }}>
                  <SectionLabel>{group.label}</SectionLabel>

                  {group.key === 'card' ? (
                    rows.map((card) => <CardAccount key={card.id} account={card} />)
                  ) : (
                    <ListCard>
                      {rows.map((account, index) => (
                        <Box key={account.id}>
                          {index > 0 && <RowDivider />}
                          <ListRow
                            href={paths.data}
                            avatar={
                              <RowAvatar tone={TONES[account.type]}>
                                {initials(account.name)}
                              </RowAvatar>
                            }
                            title={account.name}
                            note={account.alias || TYPE_LABELS[account.type]}
                            value={account.balance}
                          />
                        </Box>
                      ))}
                    </ListCard>
                  )}
                </Box>
              );
            })}

            <Card sx={{ p: 2, borderRadius: 2.5 }}>
              <Typography sx={{ fontSize: 15, fontWeight: 800 }}>Tambah kantong</Typography>
              <Typography
                sx={{
                  mt: 0.75,
                  mb: 1.75,
                  fontSize: 13,
                  lineHeight: 1.55,
                  fontWeight: 600,
                  color: 'text.secondary',
                }}
              >
                Isi form, atau ketik di chat:{' '}
                <Box component="span" sx={{ color: 'primary.dark' }}>
                  “tambah kantong Jenius saldo 1 juta”
                </Box>
                .
              </Typography>

              <Stack direction="row" sx={{ gap: 1 }}>
                <Button
                  fullWidth
                  variant="outlined"
                  color="inherit"
                  onClick={() => setFormOpen(true)}
                  sx={{ minHeight: 44, borderRadius: 999, fontWeight: 800 }}
                >
                  Isi form
                </Button>
                <Button
                  fullWidth
                  component={RouterLink}
                  href={paths.chat}
                  sx={{
                    minHeight: 44,
                    borderRadius: 999,
                    fontWeight: 800,
                    color: 'primary.darker',
                    bgcolor: 'primary.lighter',
                  }}
                >
                  Lewat chat
                </Button>
              </Stack>
            </Card>
          </>
        )}
      </BoardBody>

      <WalletForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onCreated={() => {
          setFormOpen(false);
          load();
        }}
      />
    </>
  );
}

// ----------------------------------------------------------------------

/**
 * A credit card gets its own card rather than a list row. It carries a
 * limit and a bar, and the one thing it must never do is let the unused
 * limit read as money.
 */
function CardAccount({ account }) {
  const limit = account.credit_limit ?? 0;
  const used = limit ? (account.debt / limit) * 100 : 0;

  return (
    <Card sx={{ p: 2, borderRadius: 2.5 }}>
      <Stack direction="row" sx={{ gap: 1.75, alignItems: 'center' }}>
        <RowAvatar tone="ink" icon="lega:card" />

        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography noWrap sx={{ fontSize: 15, fontWeight: 700 }}>
            {account.name}
          </Typography>
          <Typography sx={{ fontSize: 12, fontWeight: 700, color: 'error.dark' }}>
            Tagihan berjalan
          </Typography>
        </Box>

        <Money amount={-account.debt} sx={{ fontSize: 16, fontWeight: 800, color: 'error.dark' }} />
      </Stack>

      {limit > 0 && (
        <>
          <Box sx={{ mt: 1.75 }}>
            <Bar value={used} tone="ink" />
          </Box>

          <Typography sx={{ mt: 1, fontSize: 12, fontWeight: 600, color: 'text.secondary' }}>
            Kepakai {formatRupiahPlain(account.debt)} dari limit {formatRupiahPlain(limit)}
          </Typography>

          <Box sx={{ mt: 1.5 }}>
            <BoardNote>
              Sisa limit {formatRupiahPlain(limit - account.debt)} tidak ikut dihitung di mana pun.
              Limit itu izin ngutang, bukan uang lu.
            </BoardNote>
          </Box>
        </>
      )}
    </Card>
  );
}
