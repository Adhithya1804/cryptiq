/** The Cryptiq logotype mark, taken verbatim from the design source. */
export function CryptiqMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ flex: 'none' }} aria-hidden focusable="false">
      <path
        d="M81.1,18.9 L50,6 L18.9,18.9 L6,50 L18.9,81.1 L50,94 L81.1,81.1 L67,67 L50,74 L33,67 L26,50 L33,33 L50,26 L67,33 Z"
        fill="#F2F2F3"
      />
      <path d="M81.1,18.9 L67,33 L73,29 Z" fill="#75777D" />
      <path d="M81.1,81.1 L67,67 L73,71 Z" fill="#75777D" />
      <line x1="46" y1="50" x2="54" y2="50" stroke="#0A0A0B" strokeWidth="1.6" />
      <line x1="50" y1="46" x2="50" y2="54" stroke="#0A0A0B" strokeWidth="1.6" />
    </svg>
  );
}
