import { describe, expect, it } from 'vitest';
import {
  fileName,
  formatCount,
  formatDuration,
  lineRange,
  pluralize,
  shortCommit,
  shortenPath,
} from './format';

describe('format helpers', () => {
  it('shortCommit takes the first 10 characters', () => {
    expect(shortCommit('1f903f5e9d8de0c4b2a1')).toBe('1f903f5e9d');
    expect(shortCommit('abc123')).toBe('abc123');
  });

  it('shortenPath keeps the last two segments and preserves short paths', () => {
    expect(shortenPath('src/cryptography/hazmat/primitives/asymmetric/rsa.py')).toBe('asymmetric/rsa.py');
    expect(shortenPath('rsa.py')).toBe('rsa.py');
    expect(shortenPath('a/b')).toBe('a/b');
  });

  it('fileName returns the final path segment', () => {
    expect(fileName('src/a/b/keys.py')).toBe('keys.py');
  });

  it('lineRange collapses equal bounds', () => {
    expect(lineRange(42, 42)).toBe('42');
    expect(lineRange(42, 47)).toBe('42–47');
    expect(lineRange(42, null)).toBe('42');
  });

  it('pluralize switches on count', () => {
    expect(pluralize(1, 'finding')).toBe('1 finding');
    expect(pluralize(0, 'finding')).toBe('0 findings');
    expect(pluralize(3, 'finding')).toBe('3 findings');
  });

  it('formatDuration renders compact human durations', () => {
    expect(formatDuration(900)).toBe('900ms');
    expect(formatDuration(1900)).toBe('1.9s');
    expect(formatDuration(45_000)).toBe('45s');
    expect(formatDuration(72_000)).toBe('1m 12s');
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(-5)).toBe('—');
  });

  it('formatCount handles null', () => {
    expect(formatCount(1441)).toBe('1,441');
    expect(formatCount(null)).toBe('—');
  });
});
