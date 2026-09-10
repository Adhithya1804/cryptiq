import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ConfidenceIndicator, PriorityBadge, ReviewStatusBadge } from './StatusIndicators';

describe('status indicators', () => {
  it('PriorityBadge shows the uppercase label in the priority colour', () => {
    render(<PriorityBadge priority="high" />);
    const label = screen.getByText('HIGH');
    expect(label).toHaveStyle({ color: 'var(--red)' });
  });

  it('ReviewStatusBadge maps a disposition to its label', () => {
    render(<ReviewStatusBadge status="accepted_risk" />);
    expect(screen.getByText('Accepted Risk')).toBeInTheDocument();
  });

  it('ConfidenceIndicator renders the confidence word', () => {
    render(<ConfidenceIndicator confidence="medium" />);
    expect(screen.getByText('Medium')).toBeInTheDocument();
  });
});
