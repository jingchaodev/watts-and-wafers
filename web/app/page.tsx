import { loadAllData, maxAsof, loadSignalEvents } from "@/lib/data";
import Header from "@/components/Header";
import SignalGrid from "@/components/SignalGrid";
import CompositeStrip from "@/components/CompositeStrip";
import GpuAvailability from "@/components/GpuAvailability";
import GpuPrice from "@/components/GpuPrice";
import PriceTrendSection from "@/components/PriceTrendSection";
import TokenEconomics from "@/components/TokenEconomics";
import TokenVolumeSection from "@/components/TokenVolumeSection";
import SignalEventsFeed from "@/components/SignalEventsFeed";
import Memory from "@/components/Memory";
import Footer from "@/components/Footer";

export default function Home() {
  const data = loadAllData();
  const asof = maxAsof(data);
  const signalEvents = loadSignalEvents();

  return (
    <div className="wrap">
      <Header asof={asof} />
      <main>
        <SignalGrid cards={data.signals.cards ?? []} />
        <CompositeStrip composite={data.composite} history={data.history.composite} />
        <GpuAvailability vast={data.vast} history={data.history.vast} />
        <PriceTrendSection />
        <GpuPrice
          vast={data.vast}
          neoclouds={data.neoclouds}
          hyperscaler={data.hyperscaler}
        />
        <TokenVolumeSection />
        <SignalEventsFeed signalEvents={signalEvents} />
        <TokenEconomics openrouter={data.openrouter} history={data.history.openrouter} />
        <Memory memory={data.memory} />
      </main>
      <Footer data={data} />
    </div>
  );
}
