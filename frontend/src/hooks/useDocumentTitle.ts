import { useEffect } from 'react';

const BASE_TITLE = 'Cryptiq';

/** Sets `document.title` to "<page> · Cryptiq" for the lifetime of the caller. */
export function useDocumentTitle(page: string | null | undefined): void {
  useEffect(() => {
    document.title = page ? `${page} · ${BASE_TITLE}` : BASE_TITLE;
    return () => {
      document.title = BASE_TITLE;
    };
  }, [page]);
}
