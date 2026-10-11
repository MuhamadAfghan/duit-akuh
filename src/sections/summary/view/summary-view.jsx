'use client';

import { useState, useEffect, useCallback } from 'react';

import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { paths } from 'src/routes/paths';
import { RouterLink } from 'src/routes/components';

import { formatRupiah } from 'src/utils/format-money';

import { goalsApi, budgetsApi, reportsApi, accountsApi } from 'src/lib/api';

import { Iconify } from 'src/components/iconify';

import {
  Bar,
  Money,
  TileRow,
  Loading,
  StatTile,
  HeroCard,
  BoardBody,
  FilterChip,
  BoardTitle,
  SectionLabel,
  SurfaceEmpty,
  SkeletonCard,
  SkeletonHero,
  SkeletonLine,
  SkeletonTiles,
} from '../../common';

// ----------------------------------------------------------------------

/** Bar colours, in the order categories come back. */
const SERIES = ['good', 'info', 'ink', 'warn'];

/** Only the keywords the backend resolves (domain/periods.py). */
const PERIODS = [
  { value: 'bulan_ini', label: 'Bulan ini' },
  { value: 'minggu_ini', label: 'Minggu ini' },
  { value: 'bulan_lalu', label: 'Bulan lalu' },
  { value: '30_hari', label: '30 hari' },
  { value: 'tahun_ini', label: 'Tahun ini' },
];

export function SummaryView() {
  const [data, setData] = useState(null);
  const [report, setReport] = useState(null);
  const [goals, setGoals] = useState([]);
  const [budgets, setBudgets] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState('bulan_ini');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summary, spending, goalRows, budgetReport] = await Promise.all([
        accountsApi.summary(),
        reportsApi.spending(period),
        // Six is a placeholder schedule until goals carry deposit dates;
        // it only affects the per-deposit hint, never a saved figure.
        goalsApi.list(6),
        budgetsApi.list(period),
      ]);
      setData(summary);
      setReport(spending);
      setGoals(goalRows);
      setBudgets(budgetReport);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    load();
  }, [load]);

  const biggest = report?.categories?.length
    ? Math.max(...report.categories.map((category) => category.amount))
    : 0;

  return (
    <>
      <BoardTitle
        title="Ringkasan"
        action={<FilterChip value={period} onChange={setPeriod} options={PERIODS} />}
      />

      <BoardBody>
        {loading && (
          <Loading label="Memuat ringkasan…">
            <SkeletonHero>
              <SkeletonLine w="100%" h={92} sx={{ mt: 2, bgcolor: 'grey.700' }} />
            </SkeletonHero>
            <SkeletonTiles />
            <SkeletonCard height={168} />
            <SkeletonCard height={132} />
          </Loading>
        )}
        {error && (
          <SurfaceEmpty icon="solar:danger-triangle-bold" title="Gagal memuat" body={error} />
        )}

        {!error && data && (
          <>
            <HeroCard
              label="Bebas pakai sampai akhir bulan"
              amount={data.free_to_spend}
              caption="Sisa limit kartu tidak ikut di sini. Limit bukan uang."
            >
              <Stack
                sx={{ mt: 2, p: 2, gap: 1.25, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.07)' }}
              >
                <Breakdown label="Uang cair" value={data.liquid} />
                <Breakdown label="Ditandai buat target" value={-data.allocated} />
                <Breakdown label="Utang kartu" value={-data.total_debt} />
              </Stack>
            </HeroCard>

            <TileRow>
              <StatTile label="Kekayaan bersih" amount={data.net_worth} tone="good" />
              <StatTile
                label="Masuk vs keluar"
                amount={(report?.income_total ?? 0) - (report?.expense_total ?? 0)}
                tone="plain"
              />
            </TileRow>

            {report && (
              <Card sx={{ p: 2.25, borderRadius: 2.5 }}>
                <Stack
                  direction="row"
                  sx={{ mb: 2, gap: 2, alignItems: 'baseline', justifyContent: 'space-between' }}
                >
                  {/* The period label comes from the backend, which resolves
                      it in the user's timezone, so label and figures cannot
                      disagree. */}
                  <Typography sx={{ fontSize: 16, fontWeight: 800 }}>
                    Keluar {report.label.toLowerCase()}
                  </Typography>
                  <Money amount={report.expense_total} sx={{ fontSize: 16, fontWeight: 800 }} />
                </Stack>

                {report.categories.length > 0 ? (
                  <Stack sx={{ gap: 1.75 }}>
                    {report.categories.slice(0, 5).map((category, index) => (
                      <Box key={category.name}>
                        <Stack
                          direction="row"
                          sx={{ mb: 0.75, gap: 2, justifyContent: 'space-between' }}
                        >
                          <Typography sx={{ fontSize: 13, fontWeight: 700 }}>
                            {category.name}
                          </Typography>
                          <Money
                            amount={category.amount}
                            plain
                            sx={{ fontSize: 13, fontWeight: 800 }}
                          />
                        </Stack>
                        <Bar
                          value={biggest ? (category.amount / biggest) * 100 : 0}
                          tone={SERIES[index % SERIES.length]}
                          height={12}
                        />
                      </Box>
                    ))}
                  </Stack>
                ) : (
                  <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
                    Belum ada pengeluaran pada periode ini.
                  </Typography>
                )}

                <Typography
                  sx={{
                    mt: 1.75,
                    fontSize: 12,
                    lineHeight: 1.5,
                    fontWeight: 600,
                    color: 'text.secondary',
                  }}
                >
                  Pindah antar kantong dan bayar tagihan kartu nggak masuk sini, biar nggak kehitung
                  dua kali.
                </Typography>
              </Card>
            )}

            <SectionLabel>MENU</SectionLabel>
            <MenuGrid budgets={budgets} goals={goals} />
          </>
        )}
      </BoardBody>
    </>
  );
}

// ----------------------------------------------------------------------

function Breakdown({ label, value }) {
  return (
    <Stack direction="row" sx={{ gap: 2, justifyContent: 'space-between' }}>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'grey.400' }}>{label}</Typography>
      <Typography sx={{ fontSize: 13, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
        {formatRupiah(value)}
      </Typography>
    </Stack>
  );
}

// ----------------------------------------------------------------------

/**
 * The way into the three surfaces that are not tabs.
 *
 * Each tile carries its own state rather than just a name, so the grid
 * answers "is anything wrong?" without being opened.
 */
function MenuGrid({ budgets, goals }) {
  const exceeded = budgets?.exceeded?.length ?? 0;
  const behind = goals.filter((goal) => goal.status === 'needs_adjustment').length;

  const tiles = [
    {
      href: paths.budget,
      // Not `lega:chart`: Ringkasan wears that in the tab bar, and the
      // two sit side by side in the chat's menu grid.
      icon: 'solar:chart-square-outline',
      label: 'Budget',
      hint: exceeded ? `${exceeded} kategori lewat limit` : 'Semua masih aman',
      alert: exceeded > 0,
    },
    {
      href: paths.target,
      icon: 'lega:target',
      label: 'Target',
      hint: goals.length
        ? `${goals.length} target${behind ? `, ${behind} ketinggalan` : ''}`
        : 'Belum ada target',
      alert: behind > 0,
    },
    { href: paths.simulasi, icon: 'lega:calculator', label: 'Simulasi', hint: 'Nabung & deposito' },
    // Data left the tab bar when Saya took its slot. It keeps its own
    // CSV button in its header, so the export did not move house — it
    // is one tap further in, next to the filters it exports with.
    { href: paths.data, icon: 'lega:list', label: 'Data', hint: 'Riwayat & ekspor CSV' },
  ];

  return (
    <Box sx={{ gap: 1.5, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
      {tiles.map((tile) => (
        <Card
          key={tile.label}
          {...(tile.external
            ? { component: 'a', href: tile.href }
            : { component: RouterLink, href: tile.href })}
          sx={{
            p: 2,
            gap: 1.25,
            display: 'flex',
            minHeight: 44,
            borderRadius: 2.5,
            color: 'text.primary',
            flexDirection: 'column',
            textDecoration: 'none',
          }}
        >
          <Box
            sx={{
              width: 44,
              height: 44,
              display: 'grid',
              placeItems: 'center',
              borderRadius: '50%',
              color: tile.alert ? 'error.dark' : 'primary.dark',
              bgcolor: tile.alert ? 'error.lighter' : 'primary.lighter',
            }}
          >
            <Iconify icon={tile.icon} width={21} />
          </Box>

          <Typography sx={{ fontSize: 16, fontWeight: 800 }}>{tile.label}</Typography>
          <Typography
            sx={{
              fontSize: 12,
              fontWeight: 700,
              color: tile.alert ? 'error.dark' : 'text.secondary',
            }}
          >
            {tile.hint}
          </Typography>
        </Card>
      ))}
    </Box>
  );
}
