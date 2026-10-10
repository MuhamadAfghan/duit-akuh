import { merge } from 'es-toolkit';
import { useCallback } from 'react';
import { Controller, useFormContext } from 'react-hook-form';

import TextField from '@mui/material/TextField';
import Autocomplete from '@mui/material/Autocomplete';

// ----------------------------------------------------------------------

export function RHFAutocomplete({ name, label, slotProps, helperText, placeholder, ...other }) {
  const { control, setValue } = useFormContext();

  const { textField, ...otherSlotProps } = slotProps ?? {};

  const renderInput = useCallback(
    (params, error) => {
      const { slotProps: systemSlotProps, ...otherSystemProps } = params;
      const { slotProps: externalTextFieldSlotProps, ...otherTextFieldProps } = textField || {};

      const mergedSlotProps = merge(systemSlotProps, externalTextFieldSlotProps ?? {});

      return (
        <TextField
          {...otherSystemProps}
          label={label}
          placeholder={placeholder}
          error={!!error}
          helperText={error?.message ?? helperText}
          {...otherTextFieldProps}
          slotProps={{
            ...mergedSlotProps,
            htmlInput: {
              ...mergedSlotProps.htmlInput,
              autoComplete: 'new-password',
            },
          }}
        />
      );
    },
    [helperText, label, placeholder, textField]
  );

  return (
    <Controller
      name={name}
      control={control}
      render={({ field, fieldState }) => (
        <Autocomplete
          {...field}
          id={`${name}-rhf-autocomplete`}
          onChange={(event, newValue) => setValue(name, newValue, { shouldValidate: true })}
          renderInput={(params) => renderInput(params, fieldState.error)}
          slotProps={{
            ...otherSlotProps,
            chip: {
              size: 'small',
              variant: 'soft',
              ...otherSlotProps?.chip,
            },
          }}
          {...other}
        />
      )}
    />
  );
}
