import SummaryModal from '../components/SummaryModal';

// Intelligence = the performance / analytics surface, rendered inline (asPage)
// instead of as a modal overlay. Adapts to the active system mode.
const IntelligencePage = () => (
  <div className="intel-page">
    <SummaryModal asPage />
  </div>
);

export default IntelligencePage;
