import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { remote } from '@/types/common';
import { AsyncBoundary } from './AsyncBoundary';

describe('AsyncBoundary', () => {
  it('renders the loading slot while pending', () => {
    render(
      <AsyncBoundary state={remote.loading<string[]>()} loading={<p>custom loading</p>}>
        {() => <p>data</p>}
      </AsyncBoundary>,
    );
    expect(screen.getByText('custom loading')).toBeInTheDocument();
  });

  it('renders the error state with a working retry', async () => {
    const onRetry = vi.fn();
    render(
      <AsyncBoundary state={remote.error<string[]>({ message: 'nope' })} onRetry={onRetry}>
        {() => <p>data</p>}
      </AsyncBoundary>,
    );
    expect(screen.getByText('nope')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('renders the empty slot when the success payload is blank', () => {
    render(
      <AsyncBoundary
        state={remote.success<string[]>([])}
        isEmpty={(rows) => rows.length === 0}
        empty={<p>nothing here</p>}
      >
        {() => <p>data</p>}
      </AsyncBoundary>,
    );
    expect(screen.getByText('nothing here')).toBeInTheDocument();
  });

  it('renders children for a non-empty success payload', () => {
    render(
      <AsyncBoundary state={remote.success(['a'])} isEmpty={(rows) => rows.length === 0} empty={<p>empty</p>}>
        {(rows) => <p>rows: {rows.length}</p>}
      </AsyncBoundary>,
    );
    expect(screen.getByText('rows: 1')).toBeInTheDocument();
  });
});
