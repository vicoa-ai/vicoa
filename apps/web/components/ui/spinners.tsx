import './spinners.css';
import { cn } from '@/lib/utils';

interface SpinnerProps {
  size?: number;
  className?: string;
}

export function FoldingCubeSpinner({ size = 12, className }: SpinnerProps) {
  return (
    <span
      className={cn('inline-block flex-shrink-0 text-foreground/70', className)}
      style={{ width: size, height: size }}
    >
      <span className="sk-folding-cube">
        <span className="sk-cube1 sk-cube" />
        <span className="sk-cube2 sk-cube" />
        <span className="sk-cube4 sk-cube" />
        <span className="sk-cube3 sk-cube" />
      </span>
    </span>
  );
}

export function SingleDotSpinner({ size = 8, className }: SpinnerProps) {
  return (
    <span
      className={cn('inline-block flex-shrink-0 text-foreground/70', className)}
      style={{ width: size, height: size }}
    >
      <span className="sk-single-dot" />
    </span>
  );
}

export function RotatingPlaneSpinner({ size = 12, className }: SpinnerProps) {
  return (
    <span
      className={cn('inline-block flex-shrink-0 text-foreground/70', className)}
      style={{ width: size, height: size }}
    >
      <span className="sk-rotating-plane" />
    </span>
  );
}

export function RectOrbitalSpinner({ className }: Omit<SpinnerProps, 'size'>) {
  return (
    <span className={cn('inline-block flex-shrink-0 text-foreground/70', className)}>
      <span className="sk-rect-orbital">
        <span className="sk-ro-cube" />
        <span className="sk-ro-cube" />
        <span className="sk-ro-cube" />
        <span className="sk-ro-cube" />
      </span>
    </span>
  );
}

export function DoubleBounceSpinner({ size = 12, className }: SpinnerProps) {
  return (
    <span
      className={cn('inline-block flex-shrink-0 text-foreground/70', className)}
      style={{ width: size, height: size }}
    >
      <span className="sk-double-bounce">
        <span className="sk-db-child" />
        <span className="sk-db-child sk-db-child2" />
      </span>
    </span>
  );
}

export function ThreeBouncingDotsSpinner({ className }: Omit<SpinnerProps, 'size'>) {
  return (
    <span className={cn('inline-flex flex-shrink-0 items-center text-foreground/70', className)}>
      <span className="sk-three-bounce">
        <span className="sk-bounce sk-bounce1" />
        <span className="sk-bounce sk-bounce2" />
        <span className="sk-bounce" />
      </span>
    </span>
  );
}

export function ChasingCubesSpinner({ size = 12, className }: SpinnerProps) {
  const scale = size / 16;
  return (
    <span
      className={cn('inline-block flex-shrink-0 text-foreground/70', className)}
      style={{ width: size, height: size, overflow: 'hidden' }}
    >
      <span
        className="sk-chasing-cubes"
        style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}
      >
        <span className="sk-cc-cube" />
        <span className="sk-cc-cube sk-cc-cube2" />
      </span>
    </span>
  );
}
