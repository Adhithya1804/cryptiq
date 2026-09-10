import { useId } from 'react';
import styles from './CheckBox.module.css';

export interface CheckBoxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

/** Small square checkbox (Settings › Notifications matrix). Native input for
 *  keyboard + assistive-tech support; the box is styled via CSS. */
export function CheckBox({ label, checked, onChange, disabled = false }: CheckBoxProps) {
  const id = useId();
  return (
    <span className={styles.wrap}>
      <input
        type="checkbox"
        id={id}
        className={styles.input}
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id} className={styles.box} data-checked={checked}>
        <span className="sr-only">{label}</span>
      </label>
    </span>
  );
}
