import { UploadDropzone } from "@/components/UploadDropzone";

export default function UploadPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">
          Handwritten Script Upload &amp; OCR Queue
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Upload handwritten student scripts to generate clean Pen-to-Print Markdown &amp; PDFs,
          or link a locked exam rubric for criterion-by-criterion evaluation.
        </p>
      </div>
      <UploadDropzone />
    </div>
  );
}
