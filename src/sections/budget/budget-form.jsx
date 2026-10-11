'use client';

import * as z from 'zod';
import { useForm } from 'react-hook-form';
import { useState, useEffect } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';

import Box from '@mui/material/Box';
import Alert from '@mui/material/Alert';
import Dialog from '@mui/material/Dialog';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';

import { formatRupiah } from 'src/utils/format-money';

import { budgetsApi } from 'src/lib/api';

import { Form, Field } from 'src/components/hook-form';

// ----------------------------------------------------------------------

export const BudgetSchema = z.object({
  category: z.string().min(1, { message: 'Kategori wajib diisi' }).max(120),
  amount: z.coerce
    .number({ message: 'Isi angka' })
    .int('Rupiah harus bilangan bulat')
    .positive('Limit harus lebih dari nol'),
});

// ----------------------------------------------------------------------

export function BudgetForm({ open, initial, onClose, onSaved }) {
  const [errorMessage, setErrorMessage] = useState(null);

  const editing = Boolean(initial?.category);
  const previous = initial?.amount;

  const methods = useForm({
    resolver: zodResolver(BudgetSchema),
    defaultValues: { category: '', amount: '' },
  });

  const {
    reset,
    handleSubmit,
    formState: { isSubmitting },
  } = methods;

  useEffect(() => {
    if (open) {
      reset({ category: initial?.category ?? '', amount: initial?.amount ?? '' });
      setErrorMessage(null);
    }
  }, [open, initial, reset]);

  const onSubmit = handleSubmit(async (data) => {
    setErrorMessage(null);

    try {
      await budgetsApi.set(data.category, data.amount);
      onSaved?.();
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
        <DialogTitle sx={{ pb: 1 }}>{editing ? 'Ubah budget' : 'Budget baru'}</DialogTitle>

        <DialogContent sx={{ pb: 1 }}>
          {!!errorMessage && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorMessage}
            </Alert>
          )}

          <Box sx={{ pt: 1, gap: 2.5, display: 'flex', flexDirection: 'column' }}>
            <Field.Text
              name="category"
              label="Kategori"
              placeholder="makan"
              disabled={editing}
              helperText={
                editing ? 'Kategori nggak bisa diganti — hapus lalu buat yang baru.' : undefined
              }
            />

            <Field.Text name="amount" label="Limit per bulan" type="number" />

            {/* Replacing a limit silently is how a budget quietly stops
                meaning what the user thought it meant. */}
            {editing && Number.isInteger(previous) && (
              <Typography variant="caption" sx={{ mt: -1.5, color: 'text.secondary' }}>
                Limit sekarang {formatRupiah(previous)}. Yang baru menggantikannya mulai bulan ini.
              </Typography>
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
