import { loadAllData, maxAsof } from "@/lib/data";
import Header from "@/components/Header";
import Hero from "@/components/Hero";
import GpuAvailability from "@/components/GpuAvailability";
import GpuPrice from "@/components/GpuPrice";
import PriceTrendSection from "@/components/PriceTrendSection";
import TokenEconomics from "@/components/TokenEconomics";
import TokenVolumeSection from "@/components/TokenVolumeSection";
import Memory from "@/components/Memory";
import Footer from "@/components/Footer";

export default function Home() {
  const data = loadAllData();
  const asof = maxAsof(data);

  return (
    <div className="wrap">
      <Header asof={asof} />
      <main>
        <Hero composite={data.composite} history={data.history.composite} />
        <GpuAvailability vast={data.vast} history={data.history.vast} />
        <PriceTrendSection />
        <GpuPrice
          vast={data.vast}
          neoclouds={data.neoclouds}
          hyperscaler={data.hyperscaler}
        />
        <TokenVolumeSection />
        <TokenEconomics openrouter={data.openrouter} history={data.history.openrouter} />
        <Memory memory={data.memory} />
      </main>
      <Footer />
    </div>
  );
}
