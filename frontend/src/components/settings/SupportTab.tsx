"use client";

import React, { useState } from 'react';
import { LifeBuoy, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import Link from 'next/link';

export const SupportTab = () => {
    const [openFaq, setOpenFaq] = useState<number | null>(0);

    const toggleFaq = (index: number) => {
        setOpenFaq(openFaq === index ? null : index);
    };

    const faqs = [
        {
            question: "How do I configure my LLMs?",
            answer: (
                <div className="space-y-2 text-zinc-400">
                    <p>
                        Synapse supports local models (via Ollama) and cloud providers (OpenAI, Anthropic, Gemini, Groq, etc.).
                    </p>
                    <ul className="list-disc pl-5 space-y-1 text-sm">
                        <li>Go to the <Link href="/settings/models" className="text-blue-400 hover:underline">Models tab</Link>.</li>
                        <li>Enter your API keys for your preferred providers.</li>
                        <li>Select a default model for your agents to use.</li>
                    </ul>
                </div>
            )
        },
        {
            question: "How can I add custom capabilities to my agents?",
            answer: (
                <div className="space-y-3 text-zinc-400">
                    <p>There are two main ways to extend your agents' capabilities:</p>
                    <div className="bg-zinc-950 p-3 rounded border border-zinc-800">
                        <strong className="text-zinc-300 block mb-1">1. Tool Builder (Custom Python / HTTP)</strong>
                        <p className="text-sm">Write a Python script or configure an HTTP request (like n8n) in the <Link href="/settings/custom_tools" className="text-blue-400 hover:underline">Tool Builder tab</Link>.</p>
                    </div>
                    <div className="bg-zinc-950 p-3 rounded border border-zinc-800">
                        <strong className="text-zinc-300 block mb-1">2. MCP Servers</strong>
                        <p className="text-sm">Connect external tools via the Model Context Protocol in the <Link href="/settings/mcp_servers" className="text-blue-400 hover:underline">MCP Servers tab</Link>. Provide the connection command/URL, and the server's tools will be auto-registered.</p>
                    </div>
                </div>
            )
        },
        {
            question: "What is an Orchestration and how do I build one?",
            answer: (
                <div className="space-y-2 text-zinc-400">
                    <p>An Orchestration is a multi-agent workflow defined as a Directed Acyclic Graph (DAG).</p>
                    <ol className="list-decimal pl-5 space-y-1 text-sm">
                        <li>First, define specialized agents in the <Link href="/settings/agents" className="text-blue-400 hover:underline">Build Agents tab</Link>.</li>
                        <li>Then, go to the <Link href="/settings/orchestrations" className="text-blue-400 hover:underline">Orchestrations tab</Link>.</li>
                        <li>Connect your agents into a sequence or complex flow, defining how tasks and data move between them.</li>
                    </ol>
                </div>
            )
        },
        {
            question: "What is the Vault used for?",
            answer: (
                <div className="space-y-2 text-zinc-400">
                    <p>
                        The <Link href="/settings/vault" className="text-blue-400 hover:underline">Vault</Link> stores persistent files, knowledge bases, and skills. 
                    </p>
                    <p className="text-sm bg-zinc-950 p-2 rounded border border-zinc-800">
                        <strong>Pro Tip:</strong> Agents can reference vault files directly in their prompts using the <code className="text-zinc-300 bg-zinc-900 px-1 py-0.5 rounded">@[path]</code> syntax. This gives them immediate access to essential context.
                    </p>
                </div>
            )
        },
        {
            question: "Where can I view system logs?",
            answer: (
                <div className="space-y-2 text-zinc-400 text-sm">
                    <p>
                        Monitor system activity, agent executions, and tool calls in the <Link href="/settings/logs" className="text-blue-400 hover:underline">Logs tab</Link>. 
                    </p>
                    <p>
                        This is crucial for debugging complex orchestrations, tracking token usage, and ensuring everything is running smoothly.
                    </p>
                </div>
            )
        }
    ];

    return (
        <div className="space-y-8 text-zinc-300 animate-in fade-in duration-300">
            
            {/* Discord Callout */}
            <div className="bg-gradient-to-br from-[#5865F2]/20 to-zinc-900 border border-[#5865F2]/30 rounded-xl p-6 shadow-lg shadow-[#5865F2]/5">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <h2 className="text-xl font-bold text-white flex items-center gap-2 mb-2">
                            <LifeBuoy className="h-6 w-6 text-[#5865F2]" />
                            Join the Community
                        </h2>
                        <p className="text-sm text-zinc-300 max-w-xl leading-relaxed">
                            Have questions, need help debugging, or want to share your custom orchestrations? Join our active Discord community to connect with other builders.
                        </p>
                    </div>
                    <a
                        href="https://discord.gg/9UN45qyGh8"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex shrink-0 items-center gap-2 px-6 py-3 bg-[#5865F2] hover:bg-[#4752C4] text-white text-sm font-semibold rounded-lg transition-all hover:scale-105 shadow-md shadow-[#5865F2]/20"
                    >
                        Join Discord Server
                        <ExternalLink className="h-4 w-4" />
                    </a>
                </div>
            </div>

            {/* Quick Start Guide */}
            <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl overflow-hidden">
                <div className="p-6 border-b border-zinc-800/80 bg-zinc-900/60">
                    <h2 className="text-xl font-bold text-zinc-50">Quick Start Guide</h2>
                    <p className="text-sm text-zinc-400 mt-1">
                        Follow these steps to build your first multi-agent workflow.
                    </p>
                </div>
                
                <div className="p-6">
                    <div className="space-y-6">
                        
                        <div className="flex gap-4 group">
                            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300 font-bold text-sm group-hover:bg-blue-500/20 group-hover:text-blue-400 group-hover:border-blue-500/30 transition-colors">
                                1
                            </div>
                            <div className="flex-1">
                                <h3 className="text-base font-semibold text-zinc-200 mb-1 flex items-center gap-2">
                                    Configure Models
                                    <Link href="/settings/models" className="text-xs font-medium px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded transition-colors flex items-center gap-1">
                                        Go to Models <ChevronRight className="h-3 w-3" />
                                    </Link>
                                </h3>
                                <p className="text-sm text-zinc-400">Add API keys for cloud providers or select a local model via Ollama.</p>
                            </div>
                        </div>

                        <div className="flex gap-4 group">
                            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300 font-bold text-sm group-hover:bg-blue-500/20 group-hover:text-blue-400 group-hover:border-blue-500/30 transition-colors">
                                2
                            </div>
                            <div className="flex-1">
                                <h3 className="text-base font-semibold text-zinc-200 mb-1 flex items-center gap-2">
                                    Add Tools & Servers (Optional)
                                    <Link href="/settings/mcp_servers" className="text-xs font-medium px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded transition-colors flex items-center gap-1">
                                        Go to MCP <ChevronRight className="h-3 w-3" />
                                    </Link>
                                </h3>
                                <p className="text-sm text-zinc-400">Connect MCP servers or build custom tools so your agents can interact with the outside world.</p>
                            </div>
                        </div>

                        <div className="flex gap-4 group">
                            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300 font-bold text-sm group-hover:bg-blue-500/20 group-hover:text-blue-400 group-hover:border-blue-500/30 transition-colors">
                                3
                            </div>
                            <div className="flex-1">
                                <h3 className="text-base font-semibold text-zinc-200 mb-1 flex items-center gap-2">
                                    Build Agents
                                    <Link href="/settings/agents" className="text-xs font-medium px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded transition-colors flex items-center gap-1">
                                        Go to Agents <ChevronRight className="h-3 w-3" />
                                    </Link>
                                </h3>
                                <p className="text-sm text-zinc-400">Create specialized agents with specific system prompts, models, and tool capabilities.</p>
                            </div>
                        </div>

                        <div className="flex gap-4 group">
                            <div className="flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300 font-bold text-sm group-hover:bg-blue-500/20 group-hover:text-blue-400 group-hover:border-blue-500/30 transition-colors">
                                4
                            </div>
                            <div className="flex-1">
                                <h3 className="text-base font-semibold text-zinc-200 mb-1 flex items-center gap-2">
                                    Create Orchestrations
                                    <Link href="/settings/orchestrations" className="text-xs font-medium px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded transition-colors flex items-center gap-1">
                                        Go to Orchestrations <ChevronRight className="h-3 w-3" />
                                    </Link>
                                </h3>
                                <p className="text-sm text-zinc-400">Wire your agents together in a deterministic DAG to execute complex tasks efficiently.</p>
                            </div>
                        </div>

                    </div>
                </div>
            </div>

            {/* FAQ Accordion */}
            <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl overflow-hidden">
                <div className="p-6 border-b border-zinc-800/80 bg-zinc-900/60">
                    <h2 className="text-xl font-bold text-zinc-50">Frequently Asked Questions</h2>
                    <p className="text-sm text-zinc-400 mt-1 italic">
                        Note: A comprehensive documentation site is currently on the way! 
                    </p>
                </div>
                <div className="divide-y divide-zinc-800/80">
                    {faqs.map((faq, index) => (
                        <div key={index} className="bg-zinc-950/30">
                            <button
                                onClick={() => toggleFaq(index)}
                                className="w-full text-left px-6 py-4 flex items-center justify-between hover:bg-zinc-800/30 transition-colors focus:outline-none"
                            >
                                <span className="font-medium text-zinc-200 pr-4">{faq.question}</span>
                                <ChevronDown 
                                    className={`h-5 w-5 text-zinc-500 shrink-0 transition-transform duration-300 ${openFaq === index ? 'rotate-180 text-zinc-300' : ''}`} 
                                />
                            </button>
                            <div 
                                className={`overflow-hidden transition-all duration-300 ease-in-out ${openFaq === index ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'}`}
                            >
                                <div className="px-6 pb-5 pt-1">
                                    {faq.answer}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
            
            <div className="text-center pt-4 pb-8">
                <p className="text-sm font-medium text-zinc-500 bg-zinc-900/40 inline-block px-4 py-2 rounded-full border border-zinc-800/50">
                    🚀 Extensive docs are on the way!
                </p>
            </div>
        </div>
    );
};
