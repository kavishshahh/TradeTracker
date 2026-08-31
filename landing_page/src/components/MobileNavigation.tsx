"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

const APP_URL = "https://app.tradebud.xyz";

export default function MobileNavigation() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        className="menu-button"
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls="mobile-navigation"
        aria-label={open ? "Close menu" : "Open menu"}
      >
        {open ? <X size={22} /> : <Menu size={22} />}
      </button>

      {open && (
        <nav id="mobile-navigation" className="mobile-nav" aria-label="Mobile navigation">
          <a href="#features" onClick={() => setOpen(false)}>Features</a>
          <a href="#how-it-works" onClick={() => setOpen(false)}>How it works</a>
          <Link href="/tools" onClick={() => setOpen(false)}>Free tools</Link>
          <Link href="/blog" onClick={() => setOpen(false)}>Guides</Link>
          <a href={APP_URL}>Sign in</a>
          <a className="button" href={APP_URL}>Start tracking</a>
        </nav>
      )}
    </>
  );
}
