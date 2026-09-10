import styles from './Spinner.module.css';

export interface SpinnerProps {
  size?: number;
  /** "onAccent" for use on the light primary button; "default" elsewhere. */
  tone?: 'default' | 'onAccent';
  label?: string;
}

export function Spinner({ size = 16, tone = 'default', label }: SpinnerProps) {
  return (
    <span
      className={[styles.spinner, tone === 'onAccent' ? styles.onAccent : ''].filter(Boolean).join(' ')}
      style={{ width: size, height: size, borderWidth: Math.max(2, Math.round(size / 7)) }}
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}
