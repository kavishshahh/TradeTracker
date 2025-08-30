'use client';

import { ArrowRight, BarChart3, BookOpen, Calculator, Calendar, CheckCircle, Star, Target, TrendingUp } from "lucide-react";
import { useState } from "react";

// Feature highlight component
function FeatureCard({ icon: Icon, title, description }: { icon: any, title: string, description: string }) {
  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-xl p-6 border border-white/20 hover:border-white/30 transition-all duration-300 hover:transform hover:scale-105 text-center">
      <div className="bg-gradient-to-r from-blue-500 to-cyan-500 w-12 h-12 rounded-lg flex items-center justify-center mb-4 mx-auto">
        <Icon className="h-6 w-6 text-white" />
      </div>
      <h3 className="text-xl font-semibold text-white mb-3">{title}</h3>
      <p className="text-gray-300 leading-relaxed">{description}</p>
    </div>
  );
}

// Testimonial component
function TestimonialCard({ quote, author, role, rating }: { quote: string, author: string, role: string, rating: number }) {
  return (
    <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-white/10">
      <div className="flex mb-4">
        {[...Array(rating)].map((_, i) => (
          <Star key={i} className="h-5 w-5 text-yellow-400 fill-current" />
        ))}
      </div>
      <p className="text-gray-300 mb-4 italic">"{quote}"</p>
      <div>
        <p className="text-white font-semibold">{author}</p>
        <p className="text-gray-400 text-sm">{role}</p>
      </div>
    </div>
  );
}

// Benefit item component
function BenefitItem({ text }: { text: string }) {
  return (
    <div className="flex items-center space-x-3">
      <CheckCircle className="h-5 w-5 text-green-400 flex-shrink-0" />
      <span className="text-gray-300">{text}</span>
    </div>
  );
}

export default function Home() {
  const [email, setEmail] = useState('');

  const handleGetStarted = () => {
    // For now, redirect to the main app. In production, this would handle sign-up
    window.location.href = 'https://app.tradebud.xyz';
  };

  const handleEmailSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // For now, this would integrate with your email service
    // In production, you'd use a service like SendGrid, Mailgun, or your own backend
    console.log('Support request submitted:', email);
    
    // Create mailto link for immediate support
    const mailtoLink = `mailto:kavishshah30@gmail.com?subject=TradeBud Support Request&body=Hi, I need help with TradeBud. Please contact me at: ${email}`;
    window.open(mailtoLink, '_blank');
    
    setEmail('');
    alert('Opening email client. If it doesn\'t open, please email us directly at kavishshah30@gmail.com');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-slate-900 to-black">
      {/* Navigation */}
      <nav className="relative z-50 bg-black/20 backdrop-blur-md border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center space-x-2 cursor-pointer">
              <div className="bg-gradient-to-r from-blue-500 to-cyan-500 w-8 h-8 rounded-lg flex items-center justify-center">
                <BarChart3 className="h-5 w-5 text-white" />
              </div>
              <span className="text-2xl font-bold text-white">TradeBud</span>
            </div>
            <div className="hidden md:flex space-x-8">
              <a href="#features" className="text-gray-300 hover:text-white transition-colors">Features</a>
              <a href="#benefits" className="text-gray-300 hover:text-white transition-colors">Benefits</a>
              <a href="#pricing" className="text-gray-300 hover:text-white transition-colors">Pricing</a>
            </div>
            <button 
              onClick={handleGetStarted}
              className="cursor-pointer bg-gradient-to-r from-blue-500 to-cyan-600 text-white px-6 py-2 rounded-lg hover:from-blue-600 hover:to-cyan-700 transition-all duration-300 font-semibold"
            >
              Start Free
            </button>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden py-20 lg:py-32">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-600/20 to-cyan-600/20 backdrop-blur-3xl"></div>
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold text-white mb-6 leading-tight">
              Track Your Trading 
              <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent"> Journey</span>
            </h1>
            <p className="text-xl md:text-2xl text-gray-300 mb-8 max-w-3xl mx-auto leading-relaxed">
              Professional trading journal with comprehensive analytics and performance tracking. 
              Document, analyze, and learn from every trade - completely free.
            </p>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-12">
              <button 
                onClick={handleGetStarted}
                className="cursor-pointer bg-gradient-to-r from-blue-500 to-cyan-600 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:from-blue-600 hover:to-cyan-700 transition-all duration-300 transform hover:scale-105 shadow-lg hover:shadow-xl flex items-center"
              >
                Start
                <ArrowRight className="ml-2 h-5 w-5" />
              </button>
              {/* <button className="border border-white/30 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-white/10 transition-all duration-300 flex items-center">
                Watch Demo
                <ChevronRight className="ml-2 h-5 w-5" />
              </button> */}
            </div>

            {/* Features highlight */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-4xl mx-auto mt-12">
              <div className="text-center">
                <div className="text-3xl font-bold text-white mb-2">100%</div>
                <div className="text-gray-400">Free</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-white mb-2">All</div>
                <div className="text-gray-400">Features Included</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-white mb-2">No</div>
                <div className="text-gray-400">Hidden Costs</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 bg-black/20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
              Everything You Need to 
              <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent"> Succeed</span>
            </h2>
            <p className="text-xl text-gray-300 max-w-2xl mx-auto">
              Comprehensive trading tools designed by traders, for traders. Completely free with all features included.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            <FeatureCard 
              icon={BarChart3}
              title="Advanced Analytics"
              description="Real-time P&L tracking, win rates, expectancy calculations, and comprehensive performance metrics."
            />
            <FeatureCard 
              icon={Target}
              title="Risk Management"
              description="Track position sizes, risk-to-reward ratios, and maintain disciplined trading habits."
            />
            <FeatureCard 
              icon={Calendar}
              title="Trading Calendar"
              description="Visualize trading activity with interactive calendar views and daily summaries."
            />
            <FeatureCard 
              icon={TrendingUp}
              title="Performance Tracking"
              description="Monitor your equity curve, monthly returns, and track overall performance trends."
            />
            <FeatureCard 
              icon={BookOpen}
              title="Trading Journal"
              description="Document trades with rich text notes, screenshots, and searchable tags."
            />
            <FeatureCard 
              icon={Calculator}
              title="Fee Calculation"
              description="Accurate commission and fee tracking no matter your broker."
            />
          </div>
        </div>
      </section>

      {/* Benefits Section */}
      <section id="benefits" className="py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            <div>
              <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
                Why Choose 
                <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">TradeBud</span>
              </h2>
              <p className="text-xl text-gray-300 mb-8">
                A complete trading journal solution that helps you track, analyze, and improve your trading - at no cost.
              </p>
              
              <div className="space-y-6">
                <BenefitItem text="Track all your trades in one organized platform" />
                <BenefitItem text="Analyze performance with comprehensive metrics" />
                <BenefitItem text="Visualize your trading data with interactive charts" />
                <BenefitItem text="Keep detailed notes and journal entries for each trade" />
                <BenefitItem text="Monitor risk management and position sizing" />
                <BenefitItem text="Access everything completely free with no limitations" />
              </div>

              <button 
                onClick={handleGetStarted}
                className="mt-8 bg-gradient-to-r from-blue-500 to-cyan-600 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:from-blue-600 hover:to-cyan-700 transition-all duration-300 transform hover:scale-105 shadow-lg flex items-center"
              >
                Start Tracking Today
                <ArrowRight className="ml-2 h-5 w-5" />
              </button>
            </div>

            <div className="bg-gradient-to-br from-white/10 to-white/5 backdrop-blur-sm rounded-2xl p-8 border border-white/20">
              <div className="text-center mb-6">
                <BarChart3 className="h-16 w-16 text-blue-400 mx-auto mb-4" />
                <h3 className="text-2xl font-bold text-white mb-2">What You Get</h3>
              </div>
              
              <div className="grid grid-cols-2 gap-6">
                <div className="text-center">
                  <div className="text-3xl font-bold text-blue-400">∞</div>
                  <div className="text-gray-300">Unlimited Trades</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-cyan-400">All</div>
                  <div className="text-gray-300">Analytics Features</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-green-400">$0</div>
                  <div className="text-gray-300">Monthly Cost</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-blue-400">24/7</div>
                  <div className="text-gray-300">Always Available</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

 

              {/* Contact Section */}
        <section className="py-20 bg-black/20">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
              Need Help?
            </h2>
            <p className="text-xl text-gray-300 mb-8">
              Get in touch with our support team for any questions or assistance.
            </p>
            
            <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 max-w-2xl mx-auto">
              <form onSubmit={handleEmailSubmit} className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <input
                    type="text"
                    placeholder="Your Name"
                    className="w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
                    required
                  />
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Your Email"
                    className="w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
                    required
                  />
                </div>
                <textarea
                  placeholder="How can we help you?"
                  rows={4}
                  className="w-full px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:border-blue-400 resize-none"
                  required
                />
                <button
                  type="submit"
                  className="w-full bg-gradient-to-r from-blue-500 to-cyan-600 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:from-blue-600 hover:to-cyan-700 transition-all duration-300 transform hover:scale-105 shadow-lg"
                >
                  Send Message
                </button>
              </form>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-20">
          <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center"> 
          <h2 className="text-3xl md:text-5xl font-bold text-white mb-6">
            Ready to Transform Your Trading?
          </h2>
          <p className="text-xl text-gray-300 mb-8">
            Join others who are already using TradeBud to improve their performance. 
            Start your tracking today.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mb-8">
            <button 
              onClick={handleGetStarted}
              className="bg-gradient-to-r from-blue-500 to-purple-600 text-white px-10 py-4 rounded-xl text-xl font-semibold hover:from-blue-600 hover:to-purple-700 transition-all duration-300 transform hover:scale-105 shadow-lg hover:shadow-xl flex items-center"
            >
              Start Free Trial Now
              <ArrowRight className="ml-2 h-6 w-6" />
            </button>
          </div>

          {/* Email Signup */}
          <form onSubmit={handleEmailSubmit} className="max-w-md mx-auto">
            <p className="text-gray-400 mb-4">Or get notified about updates:</p>
            <div className="flex gap-3">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter your email"
                className="flex-1 px-4 py-3 rounded-lg bg-white/10 border border-white/20 text-white placeholder-gray-400 focus:outline-none focus:border-blue-400"
                required
              />
              <button
                type="submit"
                className="bg-gradient-to-r from-blue-500 to-purple-600 text-white px-6 py-3 rounded-lg hover:from-blue-600 hover:to-purple-700 transition-all duration-300 font-semibold"
              >
                Notify Me
              </button>
            </div>
          </form>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-black/40 border-t border-white/10 py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div>
              <div className="flex items-center space-x-2 mb-4">
                <div className="bg-gradient-to-r from-blue-400 to-purple-500 w-8 h-8 rounded-lg flex items-center justify-center">
                  <BarChart3 className="h-5 w-5 text-white" />
                </div>
                <span className="text-xl font-bold text-white">TradeBud</span>
              </div>
              <p className="text-gray-400">
                Professional trading journal platform for serious traders.
              </p>
            </div>
            
            <div>
              <h3 className="text-white font-semibold mb-4">Product</h3>
              <ul className="space-y-2 text-gray-400">
                <li><a href="#features" className="hover:text-white transition-colors">Features</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Pricing</a></li>
                <li><a href="#" className="hover:text-white transition-colors">API</a></li>
              </ul>
            </div>
            
            <div>
              <h3 className="text-white font-semibold mb-4">Company</h3>
              <ul className="space-y-2 text-gray-400">
                <li><a href="#" className="hover:text-white transition-colors">About</a></li>
                {/* <li><a href="#" className="hover:text-white transition-colors">Contact</a></li> */}
              </ul>
            </div>
            
            <div>
              <h3 className="text-white font-semibold mb-4">Support</h3>
              <ul className="space-y-2 text-gray-400">
                <li><a href="mailto:kavishshah30@gmail.com" className="hover:text-white transition-colors">Email Support</a></li>
                {/* <li><a href="#" className="hover:text-white transition-colors">Help Center</a></li> */}
                {/* <li><a href="#" className="hover:text-white transition-colors">Community</a></li> */}
              </ul>
            </div>
          </div>
          
          <div className="border-t border-white/10 mt-8 pt-8 text-center text-gray-400">
            <p>&copy; 2024 TradeBud. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}