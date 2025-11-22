import { useEffect, useMemo, useRef, useState } from "react";

/**
 * TextType.jsx (React) — ketik → jeda → hapus → jeda (loop)
 */
export default function TextType({
  text = [],
  typingSpeed = 75,
  deletingSpeed = 50,
  pauseEnd = 1500, // jeda saat teks sudah penuh
  pauseStart = 400, // jeda saat teks sudah kosong
  showCursor = true,
  cursorCharacter = "|",
  highlight,
  highlightClass = "text-blue-400",
  className = "",
}) {
  const phrases = useMemo(() => (Array.isArray(text) ? text : []), [text]);
  const [idx, setIdx] = useState(0); // index frasa
  const [typed, setTyped] = useState(""); // teks tampil
  const [phase, setPhase] = useState("typing"); // typing | pausing_full | deleting | pausing_empty
  const timerRef = useRef(null);

  const clearTimers = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => {
    if (!phrases.length) return;
    const current = phrases[idx % phrases.length] || "";
    clearTimers();

    if (phase === "typing") {
      timerRef.current = setInterval(() => {
        setTyped((t) => {
          if (t.length < current.length) return current.slice(0, t.length + 1);
          // Sudah penuh → pindah ke jeda penuh
          clearTimers();
          setPhase("pausing_full");
          return t;
        });
      }, typingSpeed);
    } else if (phase === "pausing_full") {
      // Baru set timeout di fase ini (tidak keburu di-clear)
      timerRef.current = setTimeout(() => setPhase("deleting"), pauseEnd);
    } else if (phase === "deleting") {
      timerRef.current = setInterval(() => {
        setTyped((t) => {
          if (t.length > 0) return t.slice(0, -1);
          // Sudah kosong → jeda kosong
          clearTimers();
          setPhase("pausing_empty");
          return t;
        });
      }, deletingSpeed);
    } else if (phase === "pausing_empty") {
      timerRef.current = setTimeout(() => {
        setIdx((i) => (i + 1) % phrases.length);
        setPhase("typing");
      }, pauseStart);
    }

    return () => clearTimers();
  }, [phrases, idx, phase, typingSpeed, deletingSpeed, pauseEnd, pauseStart]);

  // Highlight parsial sesuai bagian yang sudah terketik/terhapus
  const renderHighlighted = () => {
    const current = phrases[idx % phrases.length] || "";
    if (!highlight) return typed;

    const fullStart = current.indexOf(highlight);
    if (fullStart === -1) return typed;

    const typedLen = typed.length;
    const before = typed.slice(0, Math.min(typedLen, fullStart));
    const hiLen = Math.min(Math.max(typedLen - fullStart, 0), highlight.length);
    const hiPart = typed.slice(fullStart, fullStart + hiLen);
    const after = typed.slice(fullStart + hiLen);

    return (
      <>
        {before}
        <span className={highlightClass}>{hiPart}</span>
        {after}
      </>
    );
  };

  return (
    <span className={className}>
      {renderHighlighted()}
      {showCursor && (
        <span
          aria-hidden
          className="inline-block animate-pulse ml-1 select-none"
        >
          {cursorCharacter}
        </span>
      )}
    </span>
  );
}
