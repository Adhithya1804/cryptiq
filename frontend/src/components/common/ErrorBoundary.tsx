import { Component, type ErrorInfo, type ReactNode } from 'react';
import styles from './StateViews.module.css';

interface Props {
  children: ReactNode;
  /** Shown in the fallback so the user knows which area failed. */
  section: string;
  /** Remounts the subtree when this value changes (e.g. the route key). */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/**
 * Section-level boundary. One failing screen shows a contained fallback instead
 * of blanking the whole app. Deliberately not global — each major area wraps its
 * own so failures stay observable and localised.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    // Kept for local diagnosis during development; no user data is logged.
    console.error(`[cryptiq] ${this.props.section} crashed`, error, info.componentStack);
  }

  private handleReset = () => this.setState({ error: null });

  override render() {
    if (this.state.error) {
      return (
        <div className={styles.wrap} role="alert">
          <div className={styles.kicker}>Unexpected error</div>
          <div className={styles.title}>{this.props.section} stopped responding</div>
          <p className={styles.body}>
            The screen hit an error it could not recover from. Reloading this section may help.
          </p>
          <div className={styles.actions}>
            <button type="button" className={styles.retry} onClick={this.handleReset}>
              Reload section
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
