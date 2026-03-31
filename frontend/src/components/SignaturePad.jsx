import React, { useEffect, useRef, useState } from "react";
import { PenLine, RotateCcw } from "lucide-react";

const CANVAS_WIDTH = 640;
const CANVAS_HEIGHT = 180;

function getCanvasPoint(event, canvas) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * CANVAS_WIDTH,
    y: ((event.clientY - rect.top) / rect.height) * CANVAS_HEIGHT,
  };
}

export default function SignaturePad({ onChange, resetKey = 0 }) {
  const canvasRef = useRef(null);
  const drawingRef = useRef(false);
  const [hasSignature, setHasSignature] = useState(false);

  const primeCanvas = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    context.strokeStyle = "#234247";
    context.lineWidth = 2.4;
    context.lineCap = "round";
    context.lineJoin = "round";
  };

  useEffect(() => {
    primeCanvas();
    onChange("");
  }, [onChange]);

  useEffect(() => {
    primeCanvas();
    setHasSignature(false);
    onChange("");
  }, [resetKey, onChange]);

  const clearSignature = () => {
    primeCanvas();
    setHasSignature(false);
    onChange("");
  };

  const startDrawing = (event) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    event.preventDefault();
    const context = canvas.getContext("2d");
    const point = getCanvasPoint(event, canvas);
    drawingRef.current = true;
    context.beginPath();
    context.moveTo(point.x, point.y);
  };

  const draw = (event) => {
    const canvas = canvasRef.current;
    if (!canvas || !drawingRef.current) return;
    event.preventDefault();
    const context = canvas.getContext("2d");
    const point = getCanvasPoint(event, canvas);
    context.lineTo(point.x, point.y);
    context.stroke();
  };

  const stopDrawing = () => {
    const canvas = canvasRef.current;
    if (!canvas || !drawingRef.current) return;
    drawingRef.current = false;
    const context = canvas.getContext("2d");
    context.closePath();
    setHasSignature(true);
    onChange(canvas.toDataURL("image/png"));
  };

  return (
    <div className="signature-pad">
      <div className="signature-pad__head">
        <div className="signature-pad__title">
          <PenLine size={16} />
          <strong>Tenant signature</strong>
        </div>
        <button className="btn btn-glass" type="button" onClick={clearSignature}>
          <RotateCcw size={16} />
          <span>Clear</span>
        </button>
      </div>

      <canvas
        ref={canvasRef}
        className="signature-pad__canvas"
        width={CANVAS_WIDTH}
        height={CANVAS_HEIGHT}
        onPointerDown={startDrawing}
        onPointerMove={draw}
        onPointerUp={stopDrawing}
        onPointerLeave={stopDrawing}
      />

      {hasSignature ? (
        <p className="signature-pad__note">
          Signature captured. The signed lease PDF will be generated and stored once you create the lease.
        </p>
      ) : null}
    </div>
  );
}
