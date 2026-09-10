import { useId } from 'react';
import styles from './SegmentedControl.module.css';

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
}

export interface SegmentedControlProps<T extends string> {
  legend: string;
  hideLegend?: boolean;
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}

/**
 * Single-select segmented control implemented as a real radio group so arrow
 * keys move between options and the selection is announced.
 */
export function SegmentedControl<T extends string>({
  legend,
  hideLegend = true,
  options,
  value,
  onChange,
  disabled = false,
}: SegmentedControlProps<T>) {
  const name = useId();
  return (
    <fieldset className={styles.group} disabled={disabled}>
      <legend className={hideLegend ? 'sr-only' : styles.legend}>{legend}</legend>
      <div className={styles.options} role="radiogroup" aria-label={legend}>
        {options.map((option) => {
          const id = `${name}-${option.value}`;
          const selected = option.value === value;
          return (
            <label key={option.value} htmlFor={id} className={styles.option} data-selected={selected}>
              <input
                type="radio"
                id={id}
                name={name}
                className="sr-only"
                checked={selected}
                onChange={() => onChange(option.value)}
              />
              {option.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
