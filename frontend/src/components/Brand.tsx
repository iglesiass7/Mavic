/**
 * La marca: logo de RYNX y el "Powered by" de DataRiders (archivos del manual
 * de marca, en public/brand). Se usan con <img>: son imágenes fijas y chicas.
 */

/* eslint-disable @next/next/no-img-element -- logos fijos: no hace falta el optimizador */

export function BrandLogo({ className }: { className?: string }) {
  return <img src="/brand/rynx-logo.png" alt="RYNX" width={692} height={164} className={className} />;
}

export function PoweredBy() {
  return (
    <div className="flex items-center justify-center gap-2">
      <span className="text-[10px] tracking-widest text-rynx-dark">Powered by</span>
      <img
        src="/brand/dataRiders-logo.png"
        alt="Data Riders"
        width={400}
        height={139}
        className="h-5 w-auto"
      />
    </div>
  );
}
