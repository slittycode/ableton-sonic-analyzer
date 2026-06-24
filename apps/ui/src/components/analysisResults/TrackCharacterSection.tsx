import { formatDisplayText } from '../../utils/displayText';
import { truncateAtSentenceBoundary } from '../analysisResultsViewModel';
import { Pill } from '../ui';
import { ResultsSectionHeader, textRoleClassName } from './shared';

export function TrackCharacterSection({ trackCharacter }: { trackCharacter: string }) {
  return (
    <section className="space-y-3">
      <ResultsSectionHeader
        title={formatDisplayText('Track Character', 'title')}
        titleRole="section-title"
        rightSlot={
          <Pill tone="neutral" variant="outline" size="sm">
            AI INTERP
          </Pill>
        }
      />
      <p data-text-role="body" className={textRoleClassName('body', 'opacity-80')}>
        {truncateAtSentenceBoundary(trackCharacter, 900)}
      </p>
    </section>
  );
}
