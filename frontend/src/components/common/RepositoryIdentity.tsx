import styles from './RepositoryIdentity.module.css';

/** Repository name with a muted secondary line (language / provider). Truncates
 *  the name; the full value stays available via `title`. */
export function RepositoryIdentity({
  name,
  secondary,
}: {
  name: string;
  secondary?: string;
}) {
  return (
    <span className={styles.identity}>
      <span className={styles.name} title={name}>
        {name}
      </span>
      {secondary && <span className={styles.secondary}>{secondary}</span>}
    </span>
  );
}
