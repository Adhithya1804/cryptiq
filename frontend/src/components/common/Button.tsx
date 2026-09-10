import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Spinner } from './Spinner';
import styles from './Button.module.css';

export type ButtonVariant =
  | 'primary'
  | 'positive'
  | 'secondary'
  | 'subtle'
  | 'accent'
  | 'danger';
export type ButtonSize = 'md' | 'sm' | 'xs';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner and blocks activation. Keeps the button in the layout. */
  loading?: boolean;
  fullWidth?: boolean;
}

/**
 * The single button primitive. `type` defaults to "button" so a button inside a
 * form never submits by accident.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    fullWidth = false,
    disabled,
    type = 'button',
    className,
    children,
    ...rest
  },
  ref,
) {
  return (
    <button
      {...rest}
      ref={ref}
      type={type}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      className={[
        styles.button,
        styles[variant],
        styles[size],
        fullWidth ? styles.fullWidth : '',
        className ?? '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {loading && <Spinner size={13} tone="onAccent" />}
      <span>{children}</span>
    </button>
  );
});
