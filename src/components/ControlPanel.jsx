import UploadPanel from "./UploadPanel";
import ProcessingPanel from "./ProcessingPanel";
import MeasurementPanel from "./MeasurementPanel";
import ExportPanel from "./ExportPanel";

export default function ControlPanel(props) {
  return (
    <aside className="control-panel">
      <div className="panel-scroll">
        <UploadPanel {...props} />
        <ProcessingPanel job={props.job} elapsed={props.elapsed} />
        {props.meshLoaded && (
          <MeasurementPanel
            isMetric={props.isMetric}
            mode={props.measurementMode}
            setMode={props.setMeasurementMode}
            result={props.measurementResult}
            measurementPoints={props.measurementPoints}
            onClear={props.clearMeasurement}
            onFinishArea={props.finishArea}
          />
        )}
        {props.meshLoaded && (
          <ExportPanel jobId={props.job?.id} meshInfo={props.meshInfo} />
        )}
      </div>
    </aside>
  );
}