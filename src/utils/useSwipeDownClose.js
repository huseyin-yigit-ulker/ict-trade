import { useCallback, useRef, useState } from 'react';

// Swipe-down-to-dismiss for mobile sheets/modals. Attach the returned `handlers`
// to a drag zone (a header or grab-handle); apply `translateY(dragY)px` to the
// sheet for live feedback. `onClose` fires when the touch is released past
// `threshold`. Touch-only — mouse/desktop never triggers it, so it's inert on web.
export function useSwipeDownClose(onClose, { threshold = 90 } = {}) {
  const startY = useRef(null);
  const [dragY, setDragY] = useState(0);

  const onTouchStart = useCallback((e) => {
    if (!e.touches || e.touches.length !== 1) { startY.current = null; return; }
    startY.current = e.touches[0].clientY;
  }, []);

  const onTouchMove = useCallback((e) => {
    if (startY.current == null) return;
    const dy = e.touches[0].clientY - startY.current;
    setDragY(dy > 0 ? dy : 0); // only downward drags move the sheet
  }, []);

  const onTouchEnd = useCallback(() => {
    if (startY.current == null) return;
    const past = dragY > threshold;
    startY.current = null;
    setDragY(0);
    if (past) onClose();
  }, [dragY, threshold, onClose]);

  return {
    dragY,
    handlers: { onTouchStart, onTouchMove, onTouchEnd, onTouchCancel: onTouchEnd },
  };
}
