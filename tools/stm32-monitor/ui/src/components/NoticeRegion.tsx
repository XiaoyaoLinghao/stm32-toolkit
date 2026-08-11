import type {JSX} from "preact";
import type {Notice} from "../state/model";

export type NoticeRegionProps={
  notices:readonly Notice[];
};

export function NoticeRegion({notices}:NoticeRegionProps):JSX.Element{
  if(notices.length===0)return<footer aria-label="Notices"/>;
  return<footer aria-label="Notices">
    <ul>{notices.map(notice=>(<li key={notice.id}>{notice.kind==="view-reset"?"View reset: ":""}{notice.text}</li>))}</ul>
  </footer>;
}
