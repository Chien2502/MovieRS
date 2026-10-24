"""Điểm minh họa chỉ hiện khi tái tạo đúng ranking đã lưu."""

import joblib
import pandas as pd
import pytest

from dashboard.services.explanations import explain_list
from src.experiments.artifacts import write_json,sha256
from src.models.research import ItemStatistics


def test_explanation_checks_payload_and_exact_recommendations(tmp_path,monkeypatch):
    import dashboard.services.explanations as module
    monkeypatch.setattr(module,'ROOT',tmp_path)
    run=tmp_path/'run_test';run.mkdir()
    write_json(run/'selection.json',{'frozen':True})
    out=tmp_path/'artifacts/resource_profiles/run_test';out.mkdir(parents=True)
    fit=pd.DataFrame({'userId':[1,1,2,3],'movieId':[1,2,2,3],'rating':[4.,4.,3.,5.]})
    path=out/'MostPopular.joblib';joblib.dump(ItemStatistics('count').fit(fit),path)
    write_json(out/'profile.json',{'selection_sha256':sha256(run/'selection.json'),
                                 'measurements':[{'model':'MostPopular','seed':None,'sha256':sha256(path)}]})
    result=explain_list({'folder':str(run)},fit,99,'MostPopular',None,[2,1])
    assert result.ranking_score.tolist()==[2,1]
    with pytest.raises(ValueError,match='danh sách'):explain_list({'folder':str(run)},fit,99,'MostPopular',None,[1,2])
    path.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='checksum'):explain_list({'folder':str(run)},fit,99,'MostPopular',None,[2,1])
