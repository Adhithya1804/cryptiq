import { forwardRef, useId, type InputHTMLAttributes } from 'react';
import styles from './TextField.module.css';

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label: string;
  /** Hide the label visually but keep it for assistive tech. */
  hideLabel?: boolean;
  error?: string;
  /** Helper text, announced with the field. */
  description?: string;
  compact?: boolean;
}

/**
 * Labelled text input with an accessible error association. The label is always
 * a real `<label htmlFor>`; the error is wired via `aria-describedby` and
 * `aria-invalid`.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hideLabel = false, error, description, compact = false, className, id, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const errorId = `${inputId}-error`;
  const descriptionId = `${inputId}-description`;
  const describedBy =
    [description ? descriptionId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;

  return (
    <div className={[styles.field, className ?? ''].filter(Boolean).join(' ')}>
      <label htmlFor={inputId} className={hideLabel ? 'sr-only' : styles.label}>
        {label}
      </label>
      {description && (
        <p id={descriptionId} className={styles.label} style={{ fontWeight: 400 }}>
          {description}
        </p>
      )}
      <input
        {...rest}
        ref={ref}
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={[styles.input, compact ? styles.compact : '', error ? styles.invalid : '']
          .filter(Boolean)
          .join(' ')}
      />
      {error && (
        <div id={errorId} className={styles.error} role="alert">
          {error}
        </div>
      )}
    </div>
  );
});
