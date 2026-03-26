import { CalendarEvent } from '@/types';

interface EventListProps {
    events: CalendarEvent[];
}

export const EventList = ({ events }: EventListProps) => {
    if (!events || events.length === 0) return null;
    return (
        <div className="mt-4 flex flex-col gap-2 w-full max-w-2xl font-mono">
            <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-2 border-b border-zinc-900 pb-1">Scheduler // Events</h3>
            <div className="flex flex-col gap-px bg-zinc-800 border border-zinc-800">
                {events.map((event) => (
                    <a
                        key={event.id}
                        href={event.htmlLink}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group flex items-center gap-4 bg-black p-4 hover:bg-zinc-900 transition-all"
                    >
                        <div className="flex flex-col items-center justify-center h-10 w-10 border border-zinc-800 text-zinc-400 group-hover:border-white group-hover:text-white transition-colors">
                            <span className="text-[8px] font-bold uppercase">{new Date(event.start).toLocaleString('default', { month: 'short' })}</span>
                            <span className="text-sm font-bold">{new Date(event.start).getDate()}</span>
                        </div>
                        <div className="flex-1">
                            <span className="block text-sm font-bold text-zinc-300 group-hover:text-white transition-colors">{event.summary}</span>
                            <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{new Date(event.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                    </a>
                ))}
            </div>
        </div>
    );
};
