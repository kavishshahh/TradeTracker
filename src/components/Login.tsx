'use client';

import { useAuth } from '@/contexts/AuthContext';
import { triggerWelcomeEmail } from '@/lib/api';
import { Eye, EyeOff, Lock, Mail, UserPlus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { toast } from 'react-toastify';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSignUp, setIsSignUp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const { signIn, signUp, signInWithGoogle } = useAuth();
  const router = useRouter();

  async function sendWelcomeEmail(address: string, name: string | undefined, isNewUser: boolean) {
    try {
      await triggerWelcomeEmail(address, name, isNewUser);
    } catch (welcomeError) {
      console.error('Failed to trigger welcome email:', welcomeError);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill in all fields');
      return;
    }

    try {
      setError('');
      setLoading(true);
      if (isSignUp) {
        await signUp(email, password);
        toast.success('Account created successfully.');
        await sendWelcomeEmail(email, undefined, true);
      } else {
        await signIn(email, password);
        toast.success('Welcome back.');
        await sendWelcomeEmail(email, undefined, false);
      }
      router.push('/');
    } catch (authError: unknown) {
      console.error('Auth error:', authError);
      const errorMessage = authError instanceof Error ? authError.message : 'Failed to authenticate';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSignIn() {
    try {
      setError('');
      setLoading(true);
      const result = await signInWithGoogle();
      const user = result.user;
      const address = user.email || '';
      const isNewUser = user.metadata.creationTime === user.metadata.lastSignInTime;
      toast.success(isNewUser ? 'Account created successfully.' : 'Welcome back.');
      await sendWelcomeEmail(address, user.displayName || undefined, isNewUser);
      router.push('/');
    } catch (authError: unknown) {
      console.error('Google sign-in error:', authError);
      const errorMessage = authError instanceof Error ? authError.message : 'Failed to sign in with Google';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-context">
        <a className="login-brand" href="https://tradebud.xyz" aria-label="TradeBud home">
          <span className="login-brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>TradeBud</span>
        </a>

        <div className="login-message">
          <p>YOUR TRADING RECORD</p>
          <h1>Review the decision,<br />not only the result.</h1>
          <span>One clear place for your trades, notes, risk, and performance.</span>
        </div>

        <div className="login-proof">
          <div><strong>Net P&amp;L</strong><span>Fees accounted for</span></div>
          <div><strong>Trading journal</strong><span>Context kept with every trade</span></div>
          <div><strong>Performance</strong><span>Patterns visible over time</span></div>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-form-wrap">
          <p className="login-kicker">{isSignUp ? 'CREATE YOUR JOURNAL' : 'WELCOME BACK'}</p>
          <h2>{isSignUp ? 'Create your account' : 'Sign in to TradeBud'}</h2>
          <p className="login-subtitle">{isSignUp ? 'Start building a useful trading record.' : 'Continue to your trading workspace.'}</p>

          <form className="login-form" onSubmit={handleSubmit}>
            {error && <div className="login-error" role="alert">{error}</div>}

            <label htmlFor="email">Email address</label>
            <div className="login-input-wrap">
              <Mail size={17} />
              <input id="email" name="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>

            <label htmlFor="password">Password</label>
            <div className="login-input-wrap">
              <Lock size={17} />
              <input id="password" name="password" type={showPassword ? 'text' : 'password'} autoComplete={isSignUp ? 'new-password' : 'current-password'} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" />
              <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Hide password' : 'Show password'}>
                {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
              </button>
            </div>

            <button type="submit" disabled={loading} className="login-primary">
              {loading ? <span className="login-spinner" /> : isSignUp ? <><UserPlus size={17} /> Create account</> : 'Sign in'}
            </button>
          </form>

          <div className="login-divider"><span>OR</span></div>
          <button type="button" onClick={handleGoogleSignIn} disabled={loading} className="google-button">
            <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Continue with Google
          </button>

          <button type="button" onClick={() => setIsSignUp(!isSignUp)} className="login-switch">
            {isSignUp ? 'Already have an account? Sign in' : 'New to TradeBud? Create an account'}
          </button>
          <p className="login-terms">By continuing, you agree to use TradeBud responsibly and keep your account secure.</p>
        </div>
      </section>
    </main>
  );
}
