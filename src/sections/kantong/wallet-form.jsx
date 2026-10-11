'use client';

import * as z from 'zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';

import { accountsApi } from 'src/lib/api';

import { Form, Field } from 'src/components/hook-form';

// ----------------------------------------------------------------------

const TYPES = [
  { value: 'bank', label: 'Rekening bank' },
  { value: 'ewallet', label: 'E-wallet' },
  { value: 'cash', label: 'Tunai' },
  { value: 'credit_card', label: 'Kartu kredit' },
];

/**
 * Rupiah on the wire must be an integer (FR03), and the API rejects a
 * float outright rather than rounding it. Coercing here keeps that
 * rejection from being the user's first hint that something is wrong.
 */
const rupiah = z.coerce
  .number({ message: 'Isi angka' })
  .int('Rupiah harus bilangan bulat')
  .min(0, 'Nggak boleh minus');

export const WalletSchema = z
  .object({
    name: z.string().min(1, { message: 'Nama kantong wajib diisi' }).max(120),
    type: z.enum(['bank', 'ewallet', 'cash', 'credit_card']),
    alias: z.string().max(60).optional(),
    opening_balance: rupiah,
    credit_limit: rupiah.optional(),
  })
  .refine((value) => value.type !== 'credit_card' || (value.credit_limit ?? 0) > 0, {
    message: 'Kartu kredit perlu limit',
    path: ['credit_limit'],
  });

// ----------------------------------------------------------------------

export function WalletForm({ open, onClose, onCreated }) {
  const [errorMessage, setErrorMessage] = useState(null);

  const methods = useForm({
    resolver: zodResolver(WalletSchema),
    defaultValues: { name: '', type: 'bank', alias: '', opening_balance: 0, credit_limit: 0 },
  });

  const {
    watch,
    reset,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  const isCard = watch('type') === 'credit_card';

  const onSubmit = handleSubmit(async (data) => {
    setErrorMessage(null);

    try {
      await accountsApi.create({
        name: data.name,
        type: data.type,
        alias: data.alias?.trim() ? data.alias.trim() : null,
        // A card's "opening balance" is debt, which the backend models
        // on the liability side; it is not something to seed here.
        opening_balance: isCard ? 0 : data.opening_balance,
        credit_limit: isCard ? data.credit_limit : null,
      });

      reset();
      onCreated?.();
    } catch (error) {
      setErrorMessage(error.message);
    }
  });

  return (
    <Dialog
      fullWidth
      maxWidth="xs"
      open={open}
      onClose={isSubmitting ? undefined : onClose}
      slotProps={{ paper: { sx: { borderRadius: 3 } } }}
    >
      <Form methods={methods} onSubmit={onSubmit}>
        <DialogTitle sx={{ pb: 1 }}>Kantong baru</DialogTitle>

        <DialogContent sx={{ pb: 1 }}>
          {!!errorMessage && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorMessage}
            </Alert>
          )}

          <Box sx={{ pt: 1, gap: 2.5, display: 'flex', flexDirection: 'column' }}>
            <Field.Text name="name" label="Nama" placeholder="BCA" />

            <Field.Select name="type" label="Jenis">
              {TYPES.map((type) => (
                <MenuItem key={type.value} value={type.value}>
                  {type.label}
                </MenuItem>
              ))}
            </Field.Select>

            <Field.Text
              name="alias"
              label="Panggilan (opsional)"
              placeholder="bca"
              helperText="Dipakai supaya chat mengenali nama pendek yang biasa lu tulis."
            />

            {isCard ? (
              <Field.Text name="credit_limit" label="Limit kartu" type="number" />
            ) : (
              <>
                <Field.Text name="opening_balance" label="Saldo awal" type="number" />
                <Typography variant="caption" sx={{ mt: -1.5, color: 'text.secondary' }}>
                  Saldo awal bukan pemasukan. Ini titik mulai, jadi laporan bulan ini nggak
                  kelihatan seperti lu baru dapat uang sebanyak itu.
                </Typography>
              </>
            )}
          </Box>
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 3 }}>
          <Button color="inherit" onClick={onClose} disabled={isSubmitting} sx={{ minHeight: 44 }}>
            Batal
          </Button>
          <Button type="submit" variant="contained" loading={isSubmitting} sx={{ minHeight: 44 }}>
            Simpan
          </Button>
        </DialogActions>
      </Form>
    </Dialog>
  );
}
