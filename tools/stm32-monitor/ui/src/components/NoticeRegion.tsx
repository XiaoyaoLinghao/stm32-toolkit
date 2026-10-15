import type {JSX} from "preact";
import type {Notice} from "../state/model";
import {copy,noticeText} from "../presentation/zh";

export type NoticeRegionProps={
  notices:readonly Notice[];
};

export function NoticeRegion({notices}:NoticeRegionProps):JSX.Element{
  if(notices.length===0)return<section className="notices" aria-label={copy.notices}/>;
  return<section className="notices" aria-label={copy.notices} aria-live="polite">
    <ul>{notices.map(notice=>(<li key={notice.id}>{noticeText(notice.text)} <details><summary>{copy.diagnostics}</summary><code>{notice.text}</code></details></li>))}</ul>
  </section>;
}
